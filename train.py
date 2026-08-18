"""FGVC-Aircraft 微调脚本 — 在 GPU 沙箱里运行。

这个文件是你的主要改动对象(agent 改的也是它)。gpurun.py 会把它上传到 GPU,
然后在 /home/ubuntu/ 目录下以 python3 train.py 运行。

训练结束后写两个文件:
  /home/ubuntu/predictions.json — 测试集预测(int 列表)。**这是唯一能换来分数的东西。**
  /home/ubuntu/report.json      — 训练脚本的自报。**这只是它自己说的话。**
最后一行必须打印:=== TRAINING DONE ===

可调节的杠杆(搜索 # TUNE 找到所有可调点):
  - BACKBONE: 骨架模型 (resnet18 / resnet50 / efficientnet_b0 / vit_b_16 …)
  - NUM_EPOCHS: 训练轮数
  - BATCH_SIZE: 批大小
  - LR: 学习率
  - FREEZE_BACKBONE: True=只训练分类头(快/省钱), False=全量微调(慢/精度高)
  - 数据增强: transforms.RandomHorizontalFlip / RandomRotation / ColorJitter 等
"""

import json
import os
import torch
import torch.nn as nn
import torch.optim as optim
import torchvision.models as models
import torchvision.transforms as transforms
from torch.utils.data import DataLoader, random_split
from torchvision.datasets import FGVCAircraft

# ── 可调超参(TUNE) ───────────────────────────────────────────────────────────

BACKBONE = "resnet18"          # TUNE: resnet18 / resnet50 / efficientnet_b0
NUM_EPOCHS = 5                 # TUNE: 训练轮数(更多 epoch = 更好精度,更贵)
BATCH_SIZE = 64                # TUNE: 批大小(A10 24GB 显存,可以开到 128-256)
LR = 3e-4                      # TUNE: 学习率(验证过能到起步线 75.7% 的值;1e-3 对全量微调偏高,容易不稳定)
FREEZE_BACKBONE = False        # TUNE: True=linear probe, False=全量微调
DATA_ROOT = os.path.expanduser("~/data")
PRED_OUT = "/home/ubuntu/predictions.json"
REPORT_OUT = "/home/ubuntu/report.json"   # 训练脚本的「自报」——过闸前不算数

N_CLASSES = 100                # FGVC-Aircraft variant 共 100 类
VAL_SPLIT = 0.15               # 从 trainval 切 15% 作为验证集
last_train_acc = 0.0
last_val_acc = 0.0

# ── 数据增强 ─────────────────────────────────────────────────────────────────

train_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.RandomCrop(224),
    transforms.RandomHorizontalFlip(),          # TUNE: 可加 RandomRotation / ColorJitter
    # transforms.RandomRotation(15),            # TUNE: 取消注释以启用旋转
    # transforms.ColorJitter(0.2, 0.2, 0.2),   # TUNE: 颜色抖动
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406],
                         [0.229, 0.224, 0.225]),
])

test_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406],
                         [0.229, 0.224, 0.225]),
])

# ── 数据集 ───────────────────────────────────────────────────────────────────

print("[data] 加载 FGVC-Aircraft (annotation_level=variant) ...")
train_ds = FGVCAircraft(
    root=DATA_ROOT,
    split="trainval",
    annotation_level="variant",
    transform=train_transform,
    download=True,
)
test_ds = FGVCAircraft(
    root=DATA_ROOT,
    split="test",
    annotation_level="variant",
    transform=test_transform,
    download=True,
)

val_size = int(len(train_ds) * VAL_SPLIT)
train_size = len(train_ds) - val_size
train_subset, val_subset = random_split(train_ds, [train_size, val_size])

train_loader = DataLoader(train_subset, batch_size=BATCH_SIZE, shuffle=True,
                          num_workers=0, pin_memory=True)
val_loader = DataLoader(val_subset, batch_size=BATCH_SIZE, shuffle=False,
                        num_workers=0, pin_memory=True)
test_loader = DataLoader(test_ds, batch_size=BATCH_SIZE, shuffle=False,
                         num_workers=0, pin_memory=True)

print(f"  train: {train_size} 张 | val: {val_size} 张 | test: {len(test_ds)} 张")
print(f"  类别数: {len(train_ds.classes)} (classes[0]={train_ds.classes[0]})")

# ── 模型 ─────────────────────────────────────────────────────────────────────

print(f"\n[model] 加载骨架 {BACKBONE} (pretrained=True) ...")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"  device: {device}")

# 根据 BACKBONE 名称动态构建
_backbone_fn = {
    "resnet18":       lambda: models.resnet18(weights=models.ResNet18_Weights.DEFAULT),
    "resnet50":       lambda: models.resnet50(weights=models.ResNet50_Weights.DEFAULT),
    "efficientnet_b0": lambda: models.efficientnet_b0(
                          weights=models.EfficientNet_B0_Weights.DEFAULT),
}
if BACKBONE not in _backbone_fn:
    raise ValueError(f"未知 BACKBONE: {BACKBONE}。请从以下选择: {list(_backbone_fn)}")

model = _backbone_fn[BACKBONE]()

# 替换分类头为 100 类
if hasattr(model, "fc"):           # resnet 系列
    in_features = model.fc.in_features
    model.fc = nn.Linear(in_features, N_CLASSES)
elif hasattr(model, "classifier"): # efficientnet 系列
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, N_CLASSES)
else:
    raise RuntimeError(f"不知道如何替换 {BACKBONE} 的分类头,请手动改")

# 冻结骨架(linear probe 模式)
if FREEZE_BACKBONE:
    print("  [FREEZE] 冻结骨架,只训练分类头")
    for name, param in model.named_parameters():
        if "fc" not in name and "classifier" not in name:
            param.requires_grad = False

model = model.to(device)

trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
total = sum(p.numel() for p in model.parameters())
print(f"  参数总量: {total:,} | 可训练: {trainable:,}")

# ── 训练 ─────────────────────────────────────────────────────────────────────

criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(
    [p for p in model.parameters() if p.requires_grad], lr=LR
)
# TUNE: 可改成 SGD + momentum / 加 LR scheduler
# scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=NUM_EPOCHS)

print(f"\n[train] 开始训练: epochs={NUM_EPOCHS}, lr={LR}, freeze={FREEZE_BACKBONE}")

for epoch in range(NUM_EPOCHS):
    model.train()
    running_loss = 0.0
    correct = 0
    total_samples = 0

    for batch_idx, (images, labels) in enumerate(train_loader):
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        running_loss += loss.item() * images.size(0)
        preds = outputs.argmax(dim=1)
        correct += (preds == labels).sum().item()
        total_samples += images.size(0)

        if batch_idx % 20 == 0:
            batch_acc = (preds == labels).float().mean().item()
            print(
                f"  epoch {epoch+1}/{NUM_EPOCHS} "
                f"batch {batch_idx}/{len(train_loader)} "
                f"loss={loss.item():.4f} batch_acc={batch_acc:.3f}"
            )

    epoch_loss = running_loss / total_samples
    epoch_acc = correct / total_samples
    last_train_acc = epoch_acc

    # 在验证集上评估
    model.eval()
    val_correct = 0
    val_total = 0
    with torch.no_grad():
        for images, labels in val_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            val_correct += (outputs.argmax(dim=1) == labels).sum().item()
            val_total += labels.size(0)
    val_acc = val_correct / val_total
    last_val_acc = val_acc
    model.train()

    print(f"  [epoch {epoch+1}] loss={epoch_loss:.4f} train_acc={epoch_acc:.4f} val_acc={val_acc:.4f}")
    # scheduler.step()   # TUNE: 如果启用 scheduler,取消注释

# ── 推理(测试集,按数据集顺序) ───────────────────────────────────────────────
#
# 这里只出预测,不算分。测试集的标签在服务端,不在这台机器上 ——
# 分数只能拿预测去 /challenge/submit 换。(荣誉制:别去网上翻 FGVC-Aircraft 的
# 测试标签,那样的分只证明你会搜索,不证明你会微调。)

print("\n[eval] 在测试集上推理(只出预测,不打分) ...")
model.eval()
all_preds = []

with torch.no_grad():
    for images, _ in test_loader:
        images = images.to(device)
        outputs = model(images)
        all_preds.extend(outputs.argmax(dim=1).cpu().tolist())

# ── 写出预测 ─────────────────────────────────────────────────────────────────

with open(PRED_OUT, "w") as f:
    json.dump(all_preds, f)
print(f"\n[output] 预测已写入 {PRED_OUT}  (共 {len(all_preds)} 条)")

# ── 自报报告 ─────────────────────────────────────────────────────────────────
#
# 手边最现成的精度数字就是最后一轮的 train_acc,所以先报它。
# 第 5 幕的 G1 闸会拿上面那份 predictions 去服务端换一个真分,再和这里的
# claimed_accuracy 对一下 —— 对不上就是红。看看差多少。

with open(REPORT_OUT, "w") as f:
    json.dump(
        {
            "claimed_accuracy": round(last_val_acc, 4),
            "backbone": BACKBONE,
            "epochs": NUM_EPOCHS,
            "lr": LR,
            "freeze_backbone": FREEZE_BACKBONE,
            "n_predictions": len(all_preds),
        },
        f,
        ensure_ascii=False,
    )
print(f"[output] 自报报告已写入 {REPORT_OUT}  (claimed_accuracy={last_train_acc:.4f})")

# 这行是 gpurun.py 的完成信号,必须保留
print("\n=== TRAINING DONE ===")

from matplotlib import font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from adjustText import adjust_text

fm.fontManager.addfont("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
plt.rcParams["font.family"] = ["Noto Sans CJK SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# 模型: (综合价格 $/M tokens, AA指数)
data = {
    "GPT-6 Astra": (47.5, 52.7),
    "GPT-6 Sol": (9.5, 47.5),
    "Claude Fable 5.1": (32.5, 53.4),
    "Claude Opus 5.5": (15, 57.6),
    "Gemini 3.8 Flash": (1.33333, 40.9),
    "Grok 4.7": (12.6, 46.4),
    "Meta Muse Spark 1.3": (4.675, 48.1),
    "MiMo v2.6 Pro": (0.594, 46.3),
    "Kimi K3": (10.5, 43.6),
    "GLM-5.3": (7.04, 44.8),
    "GLM-5.3-Flash": (0.8, 41.8),
    "DeepSeek V4.1 Flash": (0.405, 39.5),
    "Qwen3.8-Flash-Next": (0.717, 39.8),
    "Qwen3.8-27B": (2.91125, 33.7),
}

models = list(data)
price = np.array([data[m][0] for m in models])
aa = np.array([data[m][1] for m in models], dtype=float)

# Pareto 前沿：不存在其他模型同时满足 价格<=本模型 且 AA>=本模型（严格优于至少一项）
pareto = []
for i, m in enumerate(models):
    dominated = any(
        (price[j] <= price[i]) and (aa[j] >= aa[i]) and (price[j] < price[i] or aa[j] > aa[i])
        for j in range(len(models)) if j != i
    )
    if not dominated:
        pareto.append(i)
pareto.sort(key=lambda i: price[i])
print("Pareto 前沿:", [models[i] for i in pareto])

# 拟合 AA = a + b * ln(price)，仅用 Pareto 点
b, a = np.polyfit(np.log(price[pareto]), aa[pareto], 1)
pred = a + b * np.log(price[pareto])
ss_res = np.sum((aa[pareto] - pred) ** 2)
ss_tot = np.sum((aa[pareto] - aa[pareto].mean()) ** 2)
r2 = 1 - ss_res / ss_tot
print(f"拟合: AA = {a:.4f} + {b:.4f} * ln(price), R² = {r2:.3f}")

fig, ax = plt.subplots(figsize=(11, 7.5))
ax.set_xscale("log")

x_line = np.logspace(np.log10(price.min() * 0.7), np.log10(price.max() * 1.4), 200)
ax.plot(x_line, a + b * np.log(x_line), "--", color="crimson",
        label=f"Pareto 拟合: AA = {a:.1f} + {b:.2f}·ln(P)  (R² = {r2:.3f})")

mask = np.ones(len(models), dtype=bool)
mask[pareto] = False
ax.scatter(price[mask], aa[mask], s=55, color="steelblue", zorder=3, label="非 Pareto 模型")
ax.scatter(price[pareto], aa[pareto], s=85, color="crimson", zorder=4, label="Pareto 前沿模型")

# 全部标注模型名，自动避让重叠
texts = [
    ax.annotate(m, (price[i], aa[i]), fontsize=8.5,
                color="crimson" if i in pareto else "dimgray")
    for i, m in enumerate(models)
]
ax.set_xlabel("综合价格 ($ / M tokens，对数轴)")
ax.set_ylabel("AA 指数")
ax.set_title("模型性价比：AA 指数 vs 综合价格")
ax.grid(True, which="both", alpha=0.25)
leg = ax.legend(loc="upper left", fontsize=9)
adjust_text(texts, ax=ax, expand=(1.3, 1.5), objects=[leg])
leg.set_zorder(10)
fig.tight_layout()
fig.savefig("price_vs_aa.png", dpi=150)
print("已保存 price_vs_aa.png")

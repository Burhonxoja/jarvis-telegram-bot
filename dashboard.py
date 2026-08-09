"""
Jarvis bot uchun dashboard rasmlarini (kunlik, oylik, loyihalar, jamoa) generatsiya qilish.
Matplotlib "Agg" backend orqali serverda (displaysiz) ishlaydi.
"""
from __future__ import annotations

import io
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BG = "#0F172A"
CARD = "#1E293B"
BLUE = "#3B82F6"
RED = "#EF4444"
GREEN = "#22C55E"
YELLOW = "#EAB308"
WHITE = "#F8FAFC"
GRAY = "#94A3B8"


def _style_ax(ax):
    ax.set_facecolor(CARD)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(colors=WHITE, labelsize=9)
    ax.title.set_color(WHITE)


def io_bytes_from_fig(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG, dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_daily_dashboard(vazifalar: list[dict], postlar: list[dict], get_status, get_select, get_title) -> bytes:
    """Kunlik dashboard: vazifalar holati (Boshlanmagan/Bajarilgan) va kontent-reja holati (PNG bytes)."""
    today_str = date.today().strftime("%d.%m.%Y")

    # Vazifalar holati bo'yicha hisoblash (faqat Boshlanmagan / Bajarilgan — "Jarayonda" hozircha kuzatilmaydi)
    vaz_counts = {"Not started": 0, "Done": 0}
    for v in vazifalar:
        st = get_status(v, "Holati") or "Not started"
        if st == "In progress":
            st = "Not started"
        vaz_counts[st] = vaz_counts.get(st, 0) + 1

    # Kontent statusi bo'yicha hisoblash
    post_counts = {"Reja": 0, "Yozildi": 0, "Tasdiqlandi": 0, "Joylandi": 0}
    for p in postlar:
        st = get_select(p, "Status") or "Reja"
        post_counts[st] = post_counts.get(st, 0) + 1

    fig = plt.figure(figsize=(9, 6), facecolor=BG)
    fig.suptitle(f"Kunlik Dashboard — {today_str}", color=WHITE, fontsize=18, fontweight="bold")

    ax1 = fig.add_subplot(1, 2, 1)
    _style_ax(ax1)
    labels1 = ["Boshlanmagan", "Bajarilgan"]
    values1 = [vaz_counts["Not started"], vaz_counts["Done"]]
    colors1 = [GRAY, GREEN]
    bars1 = ax1.bar(labels1, values1, color=colors1)
    ax1.set_title(f"Vazifalar (jami {sum(values1)})", fontsize=12, pad=14)
    ax1.set_ylim(0, max(values1 + [1]) * 1.25)
    for b, v in zip(bars1, values1):
        ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + max(values1 + [1]) * 0.04, str(v), ha="center", color=WHITE, fontsize=11)

    ax2 = fig.add_subplot(1, 2, 2)
    _style_ax(ax2)
    labels2 = ["Reja", "Yozildi", "Tasdiq.", "Joylandi"]
    values2 = [post_counts["Reja"], post_counts["Yozildi"], post_counts["Tasdiqlandi"], post_counts["Joylandi"]]
    colors2 = [GRAY, YELLOW, BLUE, GREEN]
    bars2 = ax2.bar(labels2, values2, color=colors2)
    ax2.set_title(f"Kontent postlari (jami {sum(values2)})", fontsize=12, pad=14)
    ax2.set_ylim(0, max(values2 + [1]) * 1.25)
    for b, v in zip(bars2, values2):
        ax2.text(b.get_x() + b.get_width() / 2, b.get_height() + max(values2 + [1]) * 0.04, str(v), ha="center", color=WHITE, fontsize=11)

    fig.subplots_adjust(top=0.80, wspace=0.35)
    fig.patch.set_facecolor(BG)
    return io_bytes_from_fig(fig)


def render_monthly_dashboard(yonalishlar: list[dict], get_title, get_rich_text, get_number) -> bytes:
    """Oylik dashboard: har bir yo'nalish uchun Target vs Bajarildi progress-bar (PNG bytes)."""
    names, progresses, targets, done = [], [], [], []
    for y in yonalishlar:
        nomi = get_title(y, "Yo'nalish")
        tgt = get_number(y, "Target (son)") or 0
        bjr = get_number(y, "Bajarildi (son)") or 0
        foiz = round((bjr / tgt) * 100) if tgt else 0
        names.append(nomi)
        progresses.append(min(foiz, 100))
        targets.append(tgt)
        done.append(bjr)

    if not names:
        names, progresses, targets, done = ["Ma'lumot yo'q"], [0], [0], [0]

    fig, ax = plt.subplots(figsize=(9, max(3, 0.8 * len(names))), facecolor=BG)
    _style_ax(ax)
    y_pos = range(len(names))

    ax.barh(y_pos, [100] * len(names), color=CARD, height=0.5)
    bar_colors = [GREEN if p >= 100 else (BLUE if p >= 50 else YELLOW) for p in progresses]
    ax.barh(y_pos, progresses, color=bar_colors, height=0.5)

    for i, (p, t, d) in enumerate(zip(progresses, targets, done)):
        ax.text(102, i, f"{d}/{t}  ({p}%)", va="center", color=WHITE, fontsize=10)

    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(names, color=WHITE, fontsize=11)
    ax.set_xlim(0, 130)
    ax.set_xticks([])
    ax.invert_yaxis()
    fig.suptitle("Oylik Target Dashboard", color=WHITE, fontsize=18, fontweight="bold")

    fig.patch.set_facecolor(BG)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG, bbox_inches="tight", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def render_loyiha_dashboard(loyihalar: list[dict]) -> bytes:
    """
    Loyihalar bo'yicha oylik kelishuv/target dashboard.
    loyihalar: [{"name": str, "metrics": [(label, done, target), ...]}, ...]
    """
    if not loyihalar:
        loyihalar = [{"name": "Loyiha qo'shilmagan", "metrics": [("Ma'lumot yo'q", 0, 0)]}]

    n = len(loyihalar)
    fig, axes = plt.subplots(n, 1, figsize=(9, max(2.6, 2.3 * n)), facecolor=BG)
    if n == 1:
        axes = [axes]

    for ax, proj in zip(axes, loyihalar):
        _style_ax(ax)
        metrics = proj["metrics"]
        labels = [m[0] for m in metrics]
        done_vals = [m[1] for m in metrics]
        tgt_vals = [m[2] for m in metrics]
        progresses = [min(round((d / t) * 100), 100) if t else 0 for d, t in zip(done_vals, tgt_vals)]

        y_pos = range(len(metrics))
        ax.barh(y_pos, [100] * len(metrics), color=CARD, height=0.5)
        colors = [GREEN if p >= 100 else (BLUE if p >= 50 else YELLOW) for p in progresses]
        ax.barh(y_pos, progresses, color=colors, height=0.5)

        for i, (d, t, p) in enumerate(zip(done_vals, tgt_vals, progresses)):
            label = f"{d:g}/{t:g}  ({p}%)" if t else f"{d:g} (targetsiz)"
            ax.text(102, i, label, va="center", color=WHITE, fontsize=9)

        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(labels, color=WHITE, fontsize=10)
        ax.set_xlim(0, 135)
        ax.set_xticks([])
        ax.invert_yaxis()
        ax.set_title(proj["name"], fontsize=13, color=WHITE, loc="left", pad=10)

    fig.suptitle("📁 Loyihalar — Oylik Kelishuv", color=WHITE, fontsize=17, fontweight="bold")
    fig.patch.set_facecolor(BG)
    fig.subplots_adjust(hspace=0.75, top=1 - (0.5 / max(n, 1)), left=0.22, right=0.82)
    return io_bytes_from_fig(fig)


def render_team_donuts(team_data: list[dict]) -> bytes:
    """
    Jamoadagi bugungi ishlar — har bir xodim uchun dumaloq (donut) bajarilish foizi.
    team_data: [{"name": str, "done": int, "total": int}, ...]
    """
    if not team_data:
        team_data = [{"name": "Ma'lumot yo'q", "done": 0, "total": 0}]

    n = len(team_data)
    cols = min(n, 3)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(3.2 * cols, 3.6 * rows), facecolor=BG)

    if rows * cols == 1:
        axes_list = [axes]
    else:
        axes_list = list(axes.flat)

    for i, ax in enumerate(axes_list):
        ax.set_facecolor(BG)
        if i >= n:
            ax.axis("off")
            continue

        person = team_data[i]
        done = person["done"]
        total = person["total"]
        remaining = max(total - done, 0)
        foiz = round((done / total) * 100) if total else 0
        color = GREEN if foiz >= 100 else (BLUE if foiz >= 50 else YELLOW)

        if total == 0:
            ax.pie([1], colors=[CARD], startangle=90, wedgeprops=dict(width=0.35, edgecolor=BG))
        else:
            ax.pie([done, remaining], colors=[color, CARD], startangle=90, wedgeprops=dict(width=0.35, edgecolor=BG))

        ax.text(0, 0.12, f"{foiz}%", ha="center", va="center", color=WHITE, fontsize=17, fontweight="bold")
        ax.text(0, -0.28, f"{done}/{total}", ha="center", va="center", color=GRAY, fontsize=10)
        ax.set_title(person["name"], color=WHITE, fontsize=11, pad=8)

    fig.suptitle("👥 Jamoa — bugungi bajarilish", color=WHITE, fontsize=17, fontweight="bold")
    fig.patch.set_facecolor(BG)
    fig.subplots_adjust(top=0.82, hspace=0.6, wspace=0.4)
    return io_bytes_from_fig(fig)

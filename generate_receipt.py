#!/usr/bin/env python3
"""
買取明細（支払通知書）PDF生成スクリプト
"""

import json
import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus.flowables import HRFlowable

# ─────────────────────────────────────────────
# 発行者情報（固定）
# ─────────────────────────────────────────────
ISSUER = {
    "name":    "株式会社AiGIVE",
    "zip":     "940-0062",
    "address": "新潟県長岡市大手通2−2−6",
    "tel":     "",          # 必要なら追加
    "invoice_no": "T5110001038461",
}

# 番号管理ファイル
COUNTER_FILE = os.path.join(os.path.dirname(__file__), ".receipt_counter.json")

def load_counter():
    if os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "r") as f:
            return json.load(f).get("counter", 28)
    return 28   # 次が PN-0000000029

def save_counter(n):
    with open(COUNTER_FILE, "w") as f:
        json.dump({"counter": n}, f)

def next_receipt_number():
    n = load_counter() + 1
    save_counter(n)
    return f"PN-{n:010d}"

# ─────────────────────────────────────────────
# フォント設定（Arial Unicode：日本語・英字統一）
# ─────────────────────────────────────────────
_FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"
pdfmetrics.registerFont(TTFont("JaFont", _FONT_PATH))

FONT   = "JaFont"
FONT_B = "JaFont"

def style(size=9, bold=False, align="LEFT", color=colors.black):
    """ParagraphStyle ショートカット"""
    alignment = {"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 0)
    return ParagraphStyle(
        name="",
        fontName=FONT_B if bold else FONT,
        fontSize=size,
        leading=size * 1.5,
        textColor=color,
        alignment=alignment,
    )

def p(text, size=9, bold=False, align="LEFT", color=colors.black):
    return Paragraph(str(text), style(size, bold, align, color))

def fmt_yen(amount):
    return f"¥{amount:,.0f}"

# ─────────────────────────────────────────────
# クーポン上乗せ額の取得（T-365 / 2026-09-05）
# apps/pricing/src/lib/kaitori/coupon-server.ts の couponValueForOrder と同じロジックを
# Supabase REST 経由で再現する（reserved/used のみ上乗せ対象・fail-soft で 0）。
# ─────────────────────────────────────────────
def _supabase_conf():
    """apps/pricing/.env.local から Supabase URL / service role key を読む（exec_sql.py と同じ方式）。"""
    env_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "apps", "pricing", ".env.local"
    )
    env = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env["NEXT_PUBLIC_SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"]


def fetch_coupon_bonus(order_id: str) -> int:
    """order_id（kaitori_orders.id）から、上乗せ対象クーポンの円額を取得する。
    テーブル未整備・通信失敗・クーポン無しはすべて 0（fail-soft。既存フローを壊さない）。"""
    if not order_id:
        return 0
    import urllib.request
    import urllib.parse

    try:
        url, key = _supabase_conf()
        headers = {"apikey": key, "Authorization": f"Bearer {key}"}

        def _get(path, params):
            qs = urllib.parse.urlencode(params)
            req = urllib.request.Request(f"{url}/rest/v1/{path}?{qs}", headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())

        orders = _get(
            "kaitori_orders",
            {"id": f"eq.{order_id}", "select": "coupon_id", "limit": "1"},
        )
        coupon_id = (orders[0] or {}).get("coupon_id") if orders else None
        if not coupon_id:
            return 0

        coupons = _get(
            "kaitori_coupons",
            {"id": f"eq.{coupon_id}", "select": "value_jpy,status", "limit": "1"},
        )
        if not coupons:
            return 0
        coupon = coupons[0]
        if coupon.get("status") not in ("reserved", "used"):
            return 0
        return int(coupon.get("value_jpy") or 0)
    except Exception:
        return 0  # fail-soft: DB未整備・通信失敗でも明細書生成は止めない


# ─────────────────────────────────────────────
# メイン生成関数
# ─────────────────────────────────────────────
def generate_receipt(
    date: str,          # 例: "2025年3月5日"
    recipient_name: str,        # 宛名（会社名 or 氏名）
    recipient_address: str,     # 住所（〒xxx-xxxx 住所）
    subject: str,               # 件名
    items: list,                # [{"name": "...", "qty": 1, "unit_price": 1000}, ...]
    payment_date: str = "",     # 支払予定日
    payment_method: str = "銀行振込",
    note: str = "",
    output_dir: str = None,
    receipt_number: str = None,
    honorific: str = "御中",    # 敬称：法人="御中"、個人="様"
    tax_inclusive: bool = True, # True=単価が税込み（逆算）、False=単価が税抜き（加算）
    coupon_bonus: int = 0,      # クーポン上乗せ額（円）。呼び出し側が既に把握していれば直接渡す
    order_id: str = None,       # 指定時のみ Supabase から coupon_bonus を自動取得（coupon_bonus未指定時のみ）
):
    if output_dir is None:
        output_dir = os.path.dirname(__file__)
    os.makedirs(output_dir, exist_ok=True)

    if not coupon_bonus and order_id:
        coupon_bonus = fetch_coupon_bonus(order_id)

    if receipt_number is None:
        receipt_number = next_receipt_number()

    # ファイル名
    # ファイル名は「氏名＋敬称_PN-XXX.pdf」（個人=様 / 法人=御中）。
    # なつき指示のルール。敬称なしで保存すると、お客様へそのまま渡したときに失礼になる。
    safe_name = recipient_name.replace(" ", "").replace("　", "")
    if honorific and not safe_name.endswith(honorific):
        safe_name += honorific
    filename = f"{safe_name}_{receipt_number}.pdf"
    filepath = os.path.join(output_dir, filename)

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=15*mm, bottomMargin=15*mm,
    )

    W = A4[0] - 30*mm   # 有効幅 (mm→pt 変換済み)
    story = []

    # ══════════════════════════════════════════
    # タイトル行
    # ══════════════════════════════════════════
    story.append(p("支払通知書（買取明細書）", size=16, bold=True, align="CENTER"))
    story.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════
    # 宛名ブロック（左） ／ 発行者ブロック（右）
    # ══════════════════════════════════════════
    left_block = [
        [p(f"{recipient_name}　{honorific}", size=14, bold=True)],
        [p(recipient_address, size=9)],
    ]
    left_tbl = Table(left_block, colWidths=[W * 0.55])
    left_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    right_block = [
        [p("支払通知日", size=8), p(date, size=9)],
        [p("支払通知書番号", size=8), p(receipt_number, size=9)],
        [p("", size=8), p("")],
        [p("発行者", size=8), p(ISSUER["name"], size=9, bold=True)],
        [p("", size=8), p(f"〒{ISSUER['zip']}　{ISSUER['address']}", size=8)],
        [p("適格請求書番号", size=7), p(ISSUER["invoice_no"], size=8)],
    ]
    right_tbl = Table(right_block, colWidths=[W * 0.2, W * 0.25])
    right_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTNAME", (0, 0), (-1, -1), FONT),
    ]))

    header_tbl = Table([[left_tbl, right_tbl]], colWidths=[W * 0.55, W * 0.45])
    header_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 3*mm))

    # ══════════════════════════════════════════
    # 件名
    # ══════════════════════════════════════════
    story.append(p(f"件名：{subject}", size=10, bold=True))
    story.append(Spacer(1, 5*mm))

    # ══════════════════════════════════════════
    # 集計（右寄せ）
    # ══════════════════════════════════════════
    total_taxinc = sum(item["qty"] * item["unit_price"] for item in items)
    if tax_inclusive:
        # 単価が税込み → 逆算で税抜きを算出（切り捨て）
        subtotal = int(total_taxinc / 1.1)
        tax   = total_taxinc - subtotal
        total = total_taxinc
    else:
        # 単価が税抜き → 従来通り加算
        subtotal = total_taxinc
        tax   = int(subtotal * 0.10)
        total = subtotal + tax

    summary_data = [
        [p("小計（税抜）", size=9, align="RIGHT"), p(fmt_yen(subtotal), size=9, align="RIGHT")],
        [p("消費税（10%）", size=9, align="RIGHT"), p(fmt_yen(tax), size=9, align="RIGHT")],
        [p("お支払金額", size=10, bold=True, align="RIGHT"), p(fmt_yen(total), size=10, bold=True, align="RIGHT")],
    ]
    total_row_idx = 2  # 「お支払金額」行（罫線の基準に使う）

    # クーポン特典（T-365）：口コミクーポン等で振込額に上乗せがある注文のみ、合計行の直後に2行追加。
    # 明細・小計・消費税・契約合計（お支払金額）はクーポンの有無で一切変えない。
    if coupon_bonus:
        summary_data.append([
            p("クーポン特典", size=9, align="RIGHT"),
            p(f"+{fmt_yen(coupon_bonus)}", size=9, align="RIGHT"),
        ])
        summary_data.append([
            p("お振込予定額", size=10, bold=True, align="RIGHT"),
            p(fmt_yen(total + coupon_bonus), size=10, bold=True, align="RIGHT"),
        ])

    final_row_idx = len(summary_data) - 1  # 二重線を引く最終行（クーポン無し=お支払金額、有り=お振込予定額）

    col_w = W * 0.25
    summary_tbl = Table(summary_data, colWidths=[col_w, col_w])
    summary_tbl.setStyle(TableStyle([
        ("ALIGN",      (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE",  (0, total_row_idx), (-1, total_row_idx), 1, colors.black),
        ("LINEBELOW",  (0, final_row_idx), (-1, final_row_idx), 2, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
    ]))

    # 集計を右端に配置
    align_tbl = Table([[p(""), summary_tbl]], colWidths=[W * 0.5, col_w * 2])
    align_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(align_tbl)
    story.append(Spacer(1, 5*mm))

    # ══════════════════════════════════════════
    # 明細テーブル
    # ══════════════════════════════════════════
    header_row = [
        p("No",     size=9, bold=True, align="CENTER", color=colors.white),
        p("摘要",   size=9, bold=True, align="CENTER", color=colors.white),
        p("数量",   size=9, bold=True, align="CENTER", color=colors.white),
        p("単価",   size=9, bold=True, align="CENTER", color=colors.white),
        p("明細金額", size=9, bold=True, align="CENTER", color=colors.white),
    ]
    col_widths = [W * 0.06, W * 0.46, W * 0.12, W * 0.18, W * 0.18]

    detail_rows = [header_row]
    for i, item in enumerate(items, 1):
        amount = item["qty"] * item["unit_price"]
        detail_rows.append([
            p(str(i), size=9, align="CENTER"),
            p(item["name"], size=9),
            p(f'{item["qty"]:,}', size=9, align="RIGHT"),
            p(fmt_yen(item["unit_price"]), size=9, align="RIGHT"),
            p(fmt_yen(amount), size=9, align="RIGHT"),
        ])

    detail_tbl = Table(detail_rows, colWidths=col_widths, repeatRows=1)
    detail_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), colors.HexColor("#404040")),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]))
    story.append(detail_tbl)
    story.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════
    # 支払情報 ・ 備考
    # ══════════════════════════════════════════
    info_data = [
        [p("支払予定日", size=9, bold=True), p(payment_date or "別途通知", size=9)],
        [p("支払方法", size=9, bold=True), p(payment_method, size=9)],
        [p("備考", size=9, bold=True), p(note or "　", size=9)],
    ]
    info_tbl = Table(info_data, colWidths=[W * 0.2, W * 0.5])
    info_tbl.setStyle(TableStyle([
        ("GRID",         (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 4*mm))

    # ══════════════════════════════════════════
    # 内訳
    # ══════════════════════════════════════════
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 2*mm))
    breakdown_data = [
        [
            p("【内訳】", size=8, bold=True),
            p(f"10%対象（税抜）：{fmt_yen(subtotal)}", size=8),
            p(f"10%消費税：{fmt_yen(tax)}", size=8),
        ]
    ]
    breakdown_tbl = Table(breakdown_data, colWidths=[W * 0.15, W * 0.42, W * 0.43])
    breakdown_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(breakdown_tbl)

    doc.build(story)
    print(f"生成完了: {filepath}")
    return filepath


# ─────────────────────────────────────────────
# 使用例（直接実行時）
# ─────────────────────────────────────────────
if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    generate_receipt(
        date="2025年3月5日",
        recipient_name="スズラン商店",
        recipient_address="〒000-0000　（住所）",
        subject="スズラン商店様のポケモンカード買取に関する支払通知",
        items=[
            {"name": "ポケモンカード（例）", "qty": 1, "unit_price": 10000},
        ],
        payment_date="2025年3月31日",
        payment_method="銀行振込",
        note="",
        output_dir=script_dir,
    )

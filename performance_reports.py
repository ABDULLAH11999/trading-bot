from datetime import datetime, timezone
from io import BytesIO


RANGE_LABELS = {
    "last_hour": "Last Hour",
    "last_day": "Last Day",
    "last_week": "Last Week",
    "overall": "Overall",
}


def format_money(value, quote_asset="USDT"):
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(float(value)):.2f} {quote_asset}"


def format_number(value):
    return f"{float(value):.2f}"


def format_percent(value):
    prefix = "+" if value > 0 else ""
    return f"{prefix}{float(value):.2f}%"


def format_timestamp(timestamp):
    return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_report_filename(report):
    account = report["account_mode"]
    report_range = report["range"]
    generated = datetime.fromtimestamp(report["generated_at"], tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"performance-report-{account}-{report_range}-{generated}.pdf"


def build_pdf_bytes(report):
    pdf = PDFBuilder()
    stats = report["stats"]
    quote_asset = report["quote_asset"]

    pdf.add_page()
    pdf.header(
        "Scalper Bot Performance Report",
        f'{report["account_label"]} | {RANGE_LABELS.get(report["range"], "Overall")} | Generated {format_timestamp(report["generated_at"])}',
    )

    pdf.section_title("Overview")
    cards = [
        ("Net PnL", format_money(stats["net_pnl"], quote_asset)),
        ("Return", format_percent(stats["return_pct"])),
        ("Trades", str(stats["trade_count"])),
        ("Win Rate", f'{stats["win_rate"]:.2f}%'),
        ("Commissions", format_money(stats["commission_paid"], quote_asset)),
        ("Ending Capital", format_money(stats["end_equity"], quote_asset)),
    ]
    pdf.stat_cards(cards, columns=3)

    pdf.section_title("Capital Curve")
    pdf.chart(
        report["equity_curve"],
        left_label=format_money(stats["start_equity"], quote_asset),
        right_label=format_money(stats["end_equity"], quote_asset),
    )

    pdf.section_title("Session Context")
    pdf.key_value_rows([
        ("Session Started", format_timestamp(report["session_started_at"])),
        ("Last Reset", format_timestamp(report["last_reset_at"])),
        ("Range Start", format_timestamp(report["range_started_at"])),
        ("Active Positions", str(stats["active_positions"])),
        ("Best Trade", format_money(stats["best_trade"], quote_asset)),
        ("Worst Trade", format_money(stats["worst_trade"], quote_asset)),
    ])

    pdf.section_title("Trade History")
    headers = ["Closed", "Pair", "Entry", "Exit", "Amount", "Gross", "Fees", "Net"]
    rows = []
    for trade in report["trades"]:
        rows.append([
            format_timestamp(trade["closed_at"]),
            trade["symbol"],
            format_number(trade["entry_price"]),
            format_number(trade["exit_price"]),
            format_number(trade["amount"]),
            format_number(trade["gross_pnl"]),
            format_number(trade["commission_paid"]),
            format_number(trade["net_pnl"]),
        ])
    if not rows:
        rows.append(["No closed trades in this range", "", "", "", "", "", "", ""])
    pdf.table(headers, rows)

    return pdf.render()


class PDFBuilder:
    PAGE_WIDTH = 595.0
    PAGE_HEIGHT = 842.0
    MARGIN_X = 40.0
    MARGIN_TOP = 42.0
    MARGIN_BOTTOM = 42.0

    def __init__(self):
        self.pages = []
        self.current = []
        self.cursor_y = self.MARGIN_TOP

    def add_page(self):
        if self.current:
            self.pages.append("\n".join(self.current))
        self.current = []
        self.cursor_y = self.MARGIN_TOP
        self._draw_rect(0, 0, self.PAGE_WIDTH, self.PAGE_HEIGHT, fill=(0.07, 0.08, 0.12))

    def render(self):
        if self.current:
            self.pages.append("\n".join(self.current))
            self.current = []

        objects = []

        def add_object(content):
            objects.append(content)
            return len(objects)

        catalog_id = add_object("<< /Type /Catalog /Pages 2 0 R >>")
        pages_id = add_object("")
        font_regular_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        font_bold_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

        page_ids = []
        content_ids = []
        for page_content in self.pages:
            stream = page_content.encode("latin-1", errors="replace")
            content_id = add_object(f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream")
            page_id = add_object(
                f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {self.PAGE_WIDTH} {self.PAGE_HEIGHT}] "
                f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>"
            )
            content_ids.append(content_id)
            page_ids.append(page_id)

        pages_kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects[pages_id - 1] = f"<< /Type /Pages /Kids [{pages_kids}] /Count {len(page_ids)} >>"

        buffer = BytesIO()
        buffer.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        xref_positions = [0]
        for index, content in enumerate(objects, start=1):
            xref_positions.append(buffer.tell())
            buffer.write(f"{index} 0 obj\n".encode("latin-1"))
            buffer.write(content.encode("latin-1", errors="replace"))
            buffer.write(b"\nendobj\n")

        xref_start = buffer.tell()
        buffer.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        buffer.write(b"0000000000 65535 f \n")
        for position in xref_positions[1:]:
            buffer.write(f"{position:010d} 00000 n \n".encode("latin-1"))
        buffer.write(
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode(
                "latin-1"
            )
        )
        return buffer.getvalue()

    def ensure_space(self, height):
        if self.cursor_y + height <= self.PAGE_HEIGHT - self.MARGIN_BOTTOM:
            return
        self.add_page()

    def header(self, title, subtitle):
        self._draw_text(self.MARGIN_X, self.cursor_y, title, font="F2", size=22, color=(1, 1, 1))
        self.cursor_y += 24
        self._draw_text(self.MARGIN_X, self.cursor_y, subtitle, size=10, color=(0.70, 0.75, 0.82))
        self.cursor_y += 26
        self._draw_line(self.MARGIN_X, self.cursor_y, self.PAGE_WIDTH - self.MARGIN_X, self.cursor_y, color=(0.20, 0.23, 0.30))
        self.cursor_y += 20

    def section_title(self, title):
        self.ensure_space(28)
        self._draw_text(self.MARGIN_X, self.cursor_y, title, font="F2", size=14, color=(0.93, 0.95, 0.98))
        self.cursor_y += 20

    def stat_cards(self, cards, columns=3):
        gap = 12
        card_width = (self.PAGE_WIDTH - (self.MARGIN_X * 2) - (gap * (columns - 1))) / columns
        card_height = 62
        rows = [cards[index:index + columns] for index in range(0, len(cards), columns)]
        for row in rows:
            self.ensure_space(card_height + 10)
            x = self.MARGIN_X
            for label, value in row:
                self._draw_rect(x, self.cursor_y, card_width, card_height, fill=(0.10, 0.12, 0.17), stroke=(0.22, 0.26, 0.34))
                self._draw_text(x + 12, self.cursor_y + 18, label, size=9, color=(0.60, 0.67, 0.76))
                self._draw_text(x + 12, self.cursor_y + 40, value, font="F2", size=15, color=(1, 1, 1))
                x += card_width + gap
            self.cursor_y += card_height + 12

    def chart(self, points, left_label, right_label):
        height = 190
        self.ensure_space(height + 20)
        x = self.MARGIN_X
        y = self.cursor_y
        width = self.PAGE_WIDTH - self.MARGIN_X * 2
        self._draw_rect(x, y, width, height, fill=(0.09, 0.11, 0.15), stroke=(0.22, 0.26, 0.34))
        self._draw_text(x + 12, y + 18, "Capital growth from last reset / session start", size=9, color=(0.60, 0.67, 0.76))
        self._draw_text(x + 12, y + height - 12, left_label, size=9, color=(0.82, 0.85, 0.90))
        self._draw_text(x + width - 110, y + height - 12, right_label, size=9, color=(0.82, 0.85, 0.90))

        plot_x = x + 18
        plot_y = y + 32
        plot_w = width - 36
        plot_h = height - 56
        self._draw_line(plot_x, plot_y + plot_h, plot_x + plot_w, plot_y + plot_h, color=(0.22, 0.26, 0.34))
        self._draw_line(plot_x, plot_y, plot_x, plot_y + plot_h, color=(0.22, 0.26, 0.34))
        for step in range(1, 4):
            guide_y = plot_y + (plot_h / 4.0) * step
            self._draw_line(plot_x, guide_y, plot_x + plot_w, guide_y, color=(0.16, 0.18, 0.23), width=0.5)

        values = [float(point["equity"]) for point in points] if points else [0.0]
        min_value = min(values)
        max_value = max(values)
        span = max(max_value - min_value, 1.0)
        polyline = []
        for index, point in enumerate(points or [{"equity": values[0]}]):
            px = plot_x + (plot_w * index / max(len(points or [0]) - 1, 1))
            normalized = (float(point["equity"]) - min_value) / span
            py = plot_y + plot_h - (normalized * plot_h)
            polyline.append((px, py))
        if len(polyline) == 1:
            polyline.append((polyline[0][0] + 1, polyline[0][1]))
        self._draw_polyline(polyline, color=(0.24, 0.56, 0.96), width=2.1)
        last_x, last_y = polyline[-1]
        self._draw_circle(last_x, last_y, 3.0, fill=(0.07, 0.79, 0.47), stroke=(0.07, 0.79, 0.47))
        self.cursor_y += height + 12

    def key_value_rows(self, rows):
        row_height = 22
        self.ensure_space((len(rows) * row_height) + 8)
        box_height = len(rows) * row_height + 12
        self._draw_rect(self.MARGIN_X, self.cursor_y, self.PAGE_WIDTH - self.MARGIN_X * 2, box_height, fill=(0.10, 0.12, 0.17), stroke=(0.22, 0.26, 0.34))
        y = self.cursor_y + 18
        for label, value in rows:
            self._draw_text(self.MARGIN_X + 14, y, label, size=9, color=(0.60, 0.67, 0.76))
            self._draw_text(self.MARGIN_X + 180, y, value, size=10, color=(0.96, 0.97, 0.99))
            y += row_height
        self.cursor_y += box_height + 12

    def table(self, headers, rows):
        col_widths = [94, 60, 54, 54, 54, 54, 54, 54]
        usable_width = sum(col_widths)
        if usable_width > self.PAGE_WIDTH - self.MARGIN_X * 2:
            scale = (self.PAGE_WIDTH - self.MARGIN_X * 2) / usable_width
            col_widths = [width * scale for width in col_widths]

        def draw_header():
            self.ensure_space(28)
            x = self.MARGIN_X
            self._draw_rect(self.MARGIN_X, self.cursor_y, self.PAGE_WIDTH - self.MARGIN_X * 2, 24, fill=(0.12, 0.16, 0.22), stroke=(0.24, 0.28, 0.36))
            for index, header in enumerate(headers):
                self._draw_text(x + 6, self.cursor_y + 16, header, font="F2", size=8, color=(0.98, 0.99, 1.0))
                x += col_widths[index]
            self.cursor_y += 24

        draw_header()
        for row in rows:
            self.ensure_space(22)
            if self.cursor_y + 22 > self.PAGE_HEIGHT - self.MARGIN_BOTTOM:
                self.add_page()
                self.section_title("Trade History")
                draw_header()
            self._draw_rect(self.MARGIN_X, self.cursor_y, self.PAGE_WIDTH - self.MARGIN_X * 2, 20, fill=(0.09, 0.11, 0.15), stroke=(0.16, 0.19, 0.25))
            x = self.MARGIN_X
            for index, value in enumerate(row):
                self._draw_text(x + 6, self.cursor_y + 14, str(value)[:24], size=7.5, color=(0.92, 0.94, 0.98))
                x += col_widths[index]
            self.cursor_y += 20

    def _pdf_y(self, top_y):
        return self.PAGE_HEIGHT - top_y

    def _draw_text(self, x, y, text, font="F1", size=11, color=(1, 1, 1)):
        safe = (
            str(text)
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .replace("\r", " ")
            .replace("\n", " ")
        )
        pdf_y = self._pdf_y(y)
        self.current.append(f"BT /{font} {size} Tf {color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg 1 0 0 1 {x:.2f} {pdf_y:.2f} Tm ({safe}) Tj ET")

    def _draw_rect(self, x, y, width, height, fill=None, stroke=None):
        cmds = []
        if fill:
            cmds.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke:
            cmds.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
        pdf_y = self._pdf_y(y + height)
        cmds.append(f"{x:.2f} {pdf_y:.2f} {width:.2f} {height:.2f} re")
        if fill and stroke:
            cmds.append("B")
        elif fill:
            cmds.append("f")
        else:
            cmds.append("S")
        self.current.append(" ".join(cmds))

    def _draw_line(self, x1, y1, x2, y2, color=(1, 1, 1), width=1.0):
        self.current.append(
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG {width:.2f} w "
            f"{x1:.2f} {self._pdf_y(y1):.2f} m {x2:.2f} {self._pdf_y(y2):.2f} l S"
        )

    def _draw_polyline(self, points, color=(1, 1, 1), width=1.0):
        if len(points) < 2:
            return
        commands = [f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG {width:.2f} w"]
        first_x, first_y = points[0]
        commands.append(f"{first_x:.2f} {self._pdf_y(first_y):.2f} m")
        for x, y in points[1:]:
            commands.append(f"{x:.2f} {self._pdf_y(y):.2f} l")
        commands.append("S")
        self.current.append(" ".join(commands))

    def _draw_circle(self, x, y, radius, fill=None, stroke=None):
        c = 0.552284749831 * radius
        pdf_y = self._pdf_y(y)
        cmds = []
        if fill:
            cmds.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke:
            cmds.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
        cmds.append(
            f"{x:.2f} {pdf_y + radius:.2f} m "
            f"{x + c:.2f} {pdf_y + radius:.2f} {x + radius:.2f} {pdf_y + c:.2f} {x + radius:.2f} {pdf_y:.2f} c "
            f"{x + radius:.2f} {pdf_y - c:.2f} {x + c:.2f} {pdf_y - radius:.2f} {x:.2f} {pdf_y - radius:.2f} c "
            f"{x - c:.2f} {pdf_y - radius:.2f} {x - radius:.2f} {pdf_y - c:.2f} {x - radius:.2f} {pdf_y:.2f} c "
            f"{x - radius:.2f} {pdf_y + c:.2f} {x - c:.2f} {pdf_y + radius:.2f} {x:.2f} {pdf_y + radius:.2f} c"
        )
        cmds.append("B" if fill and stroke else "f" if fill else "S")
        self.current.append(" ".join(cmds))

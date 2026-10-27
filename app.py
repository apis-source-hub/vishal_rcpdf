import io
import os
import re
import base64
import requests
from flask import Flask, request, jsonify, Response, send_file

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.graphics.shapes import Drawing, Rect, String, Line

app = Flask(__name__)

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "template.html")
session = requests.Session()


def normalize_api_data(raw_data: dict) -> dict:
    d = raw_data.get("data", raw_data) if isinstance(raw_data, dict) else {}

    reg_no = d.get("regNo") or d.get("Registration_Number") or d.get("registration_number") or ""
    reg_date = d.get("regDate") or d.get("Registration_Date") or d.get("RegistrationDate") or ""
    chassis = d.get("chassis") or d.get("Chassis_Number") or ""
    engine = d.get("engine") or d.get("Engin_Number") or d.get("Engine_Number") or ""
    owner = d.get("owner") or d.get("Owner_Name") or ""
    father = d.get("ownerFatherName") or d.get("Father_Name") or ""

    address = (
        d.get("presentAddress")
        or d.get("Permanent_Address")
        or d.get("Communication_Address")
        or d.get("permAddress")
        or ""
    )

    fuel = d.get("fuelType") or d.get("Fuel_Type") or d.get("Fuel_Name") or "PETROL"
    v_class = d.get("vehicleClass") or d.get("Vehicle_Class_Core") or d.get("Vehicle_Class") or "TWO WHEELER(NT)"
    maker = d.get("manufacturer") or d.get("Make_Name") or d.get("Vahan_Make") or ""
    model = d.get("vehicle") or d.get("Model_Name") or d.get("Vahan_Model") or ""
    color = d.get("color") or d.get("Color") or "WHITE"
    seat = str(d.get("seatCapacity") or d.get("Seating_Capacity") or d.get("Vahan_Seating_Capacity") or "2")
    unladen = str(d.get("unladenWeight") or d.get("Vahan_GVW") or "110")
    cc = str(d.get("cubicCapacity") or d.get("Cubic_Capacity") or d.get("Vahan_Cubic_Capacity") or "110.00")

    m_month = str(d.get("Manufacture_Month") or "")
    m_year = str(d.get("Manufacture_Year") or d.get("Year") or "")
    mfg_my = f"{m_month}/{m_year}".strip("/") if (m_month or m_year) else d.get("manufacturerMonthYear", "")

    rto_name = d.get("RTO_Name") or d.get("CityofRegitration") or d.get("citycamal") or ""
    rto_data = d.get("rtoData", {})
    state_name = rto_data.get("statename", "") if isinstance(rto_data, dict) else ""
    if not state_name and rto_name:
        state_name = rto_name

    expiry = d.get("insuranceUpto") or d.get("Pyp_Policy_Expiry_Date") or ""

    owner_clean = "" if str(owner).upper() in ["NA", "NULL", "NONE"] else str(owner).strip()
    father_clean = "" if str(father).upper() in ["NA", "NULL", "NONE"] else str(father).strip()

    return {
        "regNo": str(reg_no).strip().upper(),
        "regDate": str(reg_date).strip().replace("-", "/"),
        "insuranceUpto": str(expiry).strip().replace("-", "/"),
        "chassis": str(chassis).replace("~", " ").strip(),
        "engine": str(engine).strip(),
        "owner": owner_clean,
        "ownerFatherName": father_clean,
        "presentAddress": str(address).strip(),
        "permAddress": str(address).strip(),
        "fuelType": str(fuel).strip().upper(),
        "vehicleClass": str(v_class).strip(),
        "manufacturer": str(maker).strip().upper(),
        "vehicle": str(model).strip().upper(),
        "color": str(color).strip().upper(),
        "seatCapacity": seat.strip(),
        "unladenWeight": unladen.strip(),
        "cubicCapacity": cc.strip(),
        "manufacturerMonthYear": mfg_my.strip(),
        "rtoData": {"statename": state_name.strip() if state_name else "India"},
        "regAuthority": str(rto_name).strip()
    }


def fetch_rc_data(vehicle_no: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json, text/plain, */*"
    }

    api_2_url = "https://vehiclev2.vk177384.workers.dev/"
    try:
        resp2 = session.get(api_2_url, params={"number": vehicle_no, "api_key": "sneha"}, headers=headers, timeout=12)
        if resp2.status_code == 200:
            data2 = resp2.json()
            if data2.get("status") == "Success" or "data" in data2 or "registration_number" in data2:
                return normalize_api_data(data2)
            elif data2.get("statusCode") == 200 and "response" in data2:
                return normalize_api_data(data2["response"])
    except Exception:
        pass

    api_1_url = "https://vahanapi.vk177384.workers.dev/"
    try:
        resp1 = session.get(api_1_url, params={"vehicle_no": vehicle_no}, headers=headers, timeout=12)
        if resp1.status_code == 200:
            data1 = resp1.json()
            if data1.get("statusCode") == 200 and "response" in data1:
                return normalize_api_data(data1["response"])
    except Exception:
        pass

    raise ValueError(f"No data found or APIs unreachable for vehicle {vehicle_no!r}")


def format_date_to_card(date_str: str) -> str:
    if not date_str:
        return ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    parts = date_str.split("/")
    if len(parts) == 3:
        try:
            day = parts[0].zfill(2)
            month_idx = int(parts[1]) - 1
            year = parts[2]
            if 0 <= month_idx < 12:
                return f"{day}-{months[month_idx]}-{year}"
        except Exception:
            pass
    return date_str


def card_issue_date(regn_dt: str) -> str:
    if not regn_dt:
        return ""
    parts = regn_dt.split("/")
    if len(parts) == 3:
        return f"{parts[1].zfill(2)}-{parts[2]}"
    return regn_dt


def split_address(address_str: str, max_chars: int = 35) -> tuple:
    if len(address_str) <= max_chars:
        return address_str, ""
    break_idx = address_str.rfind(" ", 0, max_chars)
    if break_idx == -1:
        break_idx = max_chars
    line1 = address_str[:break_idx].strip()
    line2 = address_str[break_idx:].strip()
    if len(line2) > 45:
        line2 = line2[:42] + "..."
    return line1, line2


def build_html(data: dict) -> str:
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()

    rto_data = data.get("rtoData", {})
    regn_no = data.get("regNo", "").strip()
    raw_reg_date = data.get("regDate", "").strip()
    regn_dt = format_date_to_card(raw_reg_date)
    raw_expiry = data.get("insuranceUpto", "").strip()
    validity = format_date_to_card(raw_expiry)
    chassis = data.get("chassis", "").replace("~", " ").strip()
    engine_no = data.get("engine", "").strip()
    owner_name = data.get("owner", "").strip()
    father_name = data.get("ownerFatherName", "").strip()
    if father_name.upper() == "NA":
        father_name = ""

    present_addr = data.get("presentAddress", "").strip()
    perm_addr = data.get("permAddress", "").strip()
    full_address = present_addr if len(present_addr) >= len(perm_addr) else perm_addr
    addr_line1, addr_line2 = split_address(full_address, max_chars=35)

    fuel = data.get("fuelType", "").strip().upper()
    norms = "BHARAT STAGE IV"
    veh_cat = data.get("vehicleClass", "").strip()
    maker = data.get("manufacturer", "").strip()
    model = data.get("vehicle", "").strip()
    color = data.get("color", "WHITE").strip()
    body_type = "SALOON"
    seat_cap = str(data.get("seatCapacity", "2")).strip()
    unld_wt = str(data.get("unladenWeight", "110")).strip()
    cubic_cap = str(data.get("cubicCapacity", "")).strip()
    no_cyl = "1"
    mfg_my = data.get("manufacturerMonthYear", "").strip()
    reg_authority = data.get("regAuthority", "").strip()
    issue_date = card_issue_date(raw_reg_date)
    state_name = rto_data.get("statename", "India").strip() if rto_data else "India"
    state_prefix = regn_no[:2] if len(regn_no) >= 2 else "RJ"

    html = html.replace(">Government of Rajasthan<", f">Government of {state_name}<")
    html = html.replace(">RJ06SQ4302<", f">{regn_no}<")
    html = html.replace(">27-Apr-2011<", f">{regn_dt}<")
    html = html.replace(">26-Apr-2026<", f">{validity}<")
    html = html.replace(">MD626AG45B1C19003<", f">{chassis}<")
    html = html.replace(">064CB1121025<", f">{engine_no}<")
    html = html.replace(">SH HAMID KHAN<", f">{owner_name}<")
    html = html.replace(">UMAID KHA KAYAMKHANI<", f">{father_name}<")

    html = re.sub(r'(>RJ<)', f">{state_prefix}<", html)
    html = re.sub(r'(ff1 fs2 fc0 sc0 ls0 ws0">), 311001(<)', lambda m: m.group(1) + addr_line1 + m.group(2), html)

    if addr_line2:
        pattern = r'(ff1 fs2 fc0 sc0 ls0 ws0">' + re.escape(addr_line1) + r'</div>\s*<div class="[^"]*ff1 fs2 fc0 sc0 ls0 ws0">)</div>'
        html = re.sub(pattern, lambda m: m.group(1) + addr_line2 + '</div>', html, count=1)

    html = html.replace(">PETROL<", f">{fuel}<")
    html = html.replace(">BHARAT STAGE II<", f">{norms}<")
    html = html.replace(">VEHICLE CLASS : TWO WHEELER(NT)<", f">VEHICLE CLASS : {veh_cat}<")
    html = html.replace(">TVS MOTOR COMPANY LTD<", f">{maker}<")
    html = html.replace(">TVS WEGO<", f">{model}<")
    html = html.replace(">BROWN<", f">{color}<")
    html = html.replace(">SOLO<", f">{body_type}<")
    html = html.replace(">110.00<", f">{cubic_cap}<")
    html = html.replace(">No of Cylinders : 1<", f">No of Cylinders : {no_cyl}<")
    html = html.replace(">4/2011<", f">{mfg_my}<")
    html = html.replace(">BHILWARA DTO, Rajasthan<", f">{reg_authority}<")
    html = html.replace(">Card Issue Date (04-2011)<", f">Card Issue Date ({issue_date})<")

    html = re.sub(r'(Seating in all Capacity</div>.*?ff1.*?>)2(<)', lambda m: m.group(1) + seat_cap + m.group(2), html, flags=re.DOTALL)
    html = re.sub(r'(Unladen Weight Kg</div>.*?ff1.*?>)110(<)', lambda m: m.group(1) + unld_wt + m.group(2), html, flags=re.DOTALL)

    return html


def generate_rc_pdf_bytes(data: dict) -> bytes:
    """Zero external dependency pure-Python PDF generator for Vercel Serverless"""
    pdf_buffer = io.BytesIO()
    c = canvas.Canvas(pdf_buffer, pagesize=A4)
    page_w, page_h = A4

    card_w = 265
    card_h = 165
    y_pos = page_h - 220
    x_left = 30
    x_right = 305

    bg_color = colors.HexColor("#D8EDF8")
    border_color = colors.HexColor("#4A7A96")

    # --- FRONT CARD ---
    c.setLineWidth(1.2)
    c.setStrokeColor(border_color)
    c.setFillColor(bg_color)
    c.roundRect(x_left, y_pos, card_w, card_h, 8, fill=1, stroke=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    state_str = data.get("rtoData", {}).get("statename", "GUJARAT").upper()
    c.drawString(x_left + 45, y_pos + card_h - 18, "Indian Union Vehicle Registration Certificate")
    c.drawString(x_left + 45, y_pos + card_h - 28, f"Issued by Government of {state_str}")

    # Front Badges
    c.setFillColor(colors.HexColor("#64D2EC"))
    c.circle(x_left + card_w - 30, y_pos + card_h - 22, 9, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#E67E22"))
    c.circle(x_left + card_w - 12, y_pos + card_h - 22, 9, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x_left + card_w - 30, y_pos + card_h - 24, "NT")
    c.drawCentredString(x_left + card_w - 12, y_pos + card_h - 24, "RJ")

    # Front Field Values
    reg_no = data.get("regNo", "")
    reg_dt = format_date_to_card(data.get("regDate", ""))
    val_dt = format_date_to_card(data.get("insuranceUpto", ""))

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_left + 45, y_pos + card_h - 45, "Regn. No")
    c.drawString(x_left + 115, y_pos + card_h - 45, "Date of Regn.")
    c.drawString(x_left + 185, y_pos + card_h - 45, "Regn. Validity")

    c.setFont("Helvetica", 7)
    c.drawString(x_left + 45, y_pos + card_h - 55, reg_no)
    c.drawString(x_left + 115, y_pos + card_h - 55, reg_dt)
    c.drawString(x_left + 185, y_pos + card_h - 55, val_dt)

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_left + 45, y_pos + card_h - 70, "Chassis Number")
    c.setFont("Helvetica", 7)
    c.drawString(x_left + 45, y_pos + card_h - 80, data.get("chassis", ""))

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_left + 45, y_pos + card_h - 93, "Engine / Motor Number")
    c.setFont("Helvetica", 7)
    c.drawString(x_left + 45, y_pos + card_h - 103, data.get("engine", ""))

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_left + 45, y_pos + card_h - 116, "Owner Name")
    c.setFont("Helvetica", 7)
    c.drawString(x_left + 45, y_pos + card_h - 126, data.get("owner", ""))

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_left + 45, y_pos + card_h - 138, "Son / Daughter / Wife of")
    c.setFont("Helvetica", 7)
    c.drawString(x_left + 45, y_pos + card_h - 147, data.get("ownerFatherName", ""))

    addr1, addr2 = split_address(data.get("presentAddress", "") or data.get("permAddress", ""), 35)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(x_left + 45, y_pos + card_h - 157, "Address : ")
    c.setFont("Helvetica", 6.5)
    c.drawString(x_left + 82, y_pos + card_h - 157, f"{addr1} {addr2}"[:50])

    # Left Vertical Info
    c.setFont("Helvetica-Bold", 6)
    c.drawString(x_left + 5, y_pos + 60, "Fuel")
    c.setFont("Helvetica", 6)
    c.drawString(x_left + 5, y_pos + 50, data.get("fuelType", "PETROL"))

    # --- BACK CARD ---
    c.setStrokeColor(border_color)
    c.setFillColor(bg_color)
    c.roundRect(x_right, y_pos, card_w, card_h, 8, fill=1, stroke=1)

    c.setFillColor(colors.HexColor("#64D2EC"))
    c.circle(x_right + 15, y_pos + card_h - 22, 9, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#E67E22"))
    c.circle(x_right + 33, y_pos + card_h - 22, 9, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x_right + 15, y_pos + card_h - 24, "NT")
    c.drawCentredString(x_right + 33, y_pos + card_h - 24, "RJ")

    v_class = data.get("vehicleClass", "M-Cycle/Scooter(2WN)")
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x_right + 50, y_pos + card_h - 24, f"VEHICLE CLASS : {v_class}")

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_right + 15, y_pos + card_h - 45, f"Regn. Number : {reg_no}")

    # Right side details
    c.drawString(x_right + 95, y_pos + card_h - 45, "Maker:")
    c.setFont("Helvetica", 7)
    c.drawString(x_right + 130, y_pos + card_h - 45, data.get("manufacturer", ""))

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_right + 95, y_pos + card_h - 60, "Model:")
    c.setFont("Helvetica", 7)
    c.drawString(x_right + 130, y_pos + card_h - 60, data.get("vehicle", ""))

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_right + 95, y_pos + card_h - 75, "Color:")
    c.setFont("Helvetica", 7)
    c.drawString(x_right + 130, y_pos + card_h - 75, data.get("color", "WHITE"))

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_right + 180, y_pos + card_h - 75, "Body Type: SALOON")

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_right + 95, y_pos + card_h - 90, "Seating Capacity:")
    c.setFont("Helvetica", 7)
    c.drawString(x_right + 165, y_pos + card_h - 90, data.get("seatCapacity", "2"))

    c.setFont("Helvetica-Bold", 7)
    c.drawString(x_right + 95, y_pos + card_h - 105, "Unladen Weight (Kg):")
    c.setFont("Helvetica", 7)
    c.drawString(x_right + 175, y_pos + card_h - 105, data.get("unladenWeight", "110"))

    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(x_right + 15, y_pos + 25, f"Mfg Month/Yr: {data.get('manufacturerMonthYear', '')}")
    c.drawString(x_right + 110, y_pos + 25, f"Cubic Cap: {data.get('cubicCapacity', '')}")
    c.drawString(x_right + 180, y_pos + 25, "Cylinders: 1")

    c.drawString(x_right + 15, y_pos + 12, f"Authority: {data.get('regAuthority', '')}")

    c.showPage()
    c.save()
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


# --- 1. DIRECT PDF DOWNLOAD ROUTE ---
@app.route("/rcdownload")
def rc_pdf_download():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
        pdf_bytes = generate_rc_pdf_bytes(data)

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"RC_{vehicle}.pdf"
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- 2. JSON RESPONSE WITH MASTER DATA & BASE64 PDF ---
@app.route("/rc")
def rc_json():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({
            "code": 400,
            "data": None,
            "message": "vehicle parameter required"
        }), 400

    try:
        data = fetch_rc_data(vehicle)
        pdf_bytes = generate_rc_pdf_bytes(data)
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        reg_no = data.get("regNo", vehicle)
        rto_code = reg_no[2:4] if len(reg_no) >= 4 and reg_no[2:4].isdigit() else ""
        state_code = reg_no[:2] if len(reg_no) >= 2 else ""
        maker = data.get("manufacturer", "")
        fuel = data.get("fuelType", "")
        cc = data.get("cubicCapacity", "")
        state_name = data.get("rtoData", {}).get("statename", "")
        zone = data.get("regAuthority", "")

        return jsonify({
            "code": 200,
            "data": {
                "masterData": [
                    {
                        "masterDpValue": f"{maker} / {fuel} / {cc} CC".strip(" /"),
                        "masterFuel": fuel,
                        "masterMake": maker,
                        "masterModel": data.get("vehicle", ""),
                        "masterModelcode": "",
                        "masterRTOCode": rto_code,
                        "masterRtoLocationCode": "",
                        "masterRtoShowVal": f"{reg_no[:4]}-{zone}" if zone else reg_no[:4],
                        "masterState": state_name,
                        "masterStateCode": "",
                        "masterStatecode": state_code,
                        "masterZonename": zone,
                        "pdf_base64": pdf_base64
                    }
                ]
            }
        }), 200

    except Exception as exc:
        return jsonify({
            "code": 500,
            "data": None,
            "message": str(exc)
        }), 500


# --- 3. RAW HTML VIEW ---
@app.route("/rchtml")
def rc_html():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
        html = build_html(data)
        return Response(html, mimetype="text/html")
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/")
def index():
    return (
        "<h2>RC Card Generator</h2>"
        "<ul>"
        "<li><code>/rcdownload?vehicle=GJ05PB4974</code> — Direct PDF Download</li>"
        "<li><code>/rc?vehicle=GJ05PB4974</code> — JSON with Base64 PDF & MasterData</li>"
        "<li><code>/rchtml?vehicle=GJ05PB4974</code> — Raw HTML</li>"
        "</ul>"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

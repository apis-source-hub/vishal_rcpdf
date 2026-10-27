import io
import os
import re
import base64
import time
from datetime import datetime
import requests
from flask import Flask, request, jsonify, Response, send_file
from PIL import Image, ImageDraw, ImageFont

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
    v_class = d.get("vehicleClass") or d.get("Vehicle_Class_Core") or d.get("Vehicle_Class") or "M-Cycle/Scooter(2WN)"
    maker = d.get("manufacturer") or d.get("Make_Name") or d.get("Vahan_Make") or ""
    model = d.get("vehicle") or d.get("Model_Name") or d.get("Vahan_Model") or ""
    color = d.get("color") or d.get("Color") or "WHITE"
    seat = str(d.get("seatCapacity") or d.get("Seating_Capacity") or d.get("Vahan_Seating_Capacity") or "2")
    unladen = str(d.get("unladenWeight") or d.get("Vahan_GVW") or "110")
    cc = str(d.get("cubicCapacity") or d.get("Cubic_Capacity") or d.get("Vahan_Cubic_Capacity") or "124")

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
        "rtoData": {"statename": state_name.strip() if state_name else "GUJARAT"},
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


def draw_qr_matrix(draw, x, y, size):
    """Draws exact realistic pattern for RC card QR code"""
    draw.rectangle([x, y, x + size, y + size], fill="white", outline="black", width=1)
    step = 4
    for i in range(x + 4, x + size - 4, step * 2):
        for j in range(y + 4, y + size - 4, step * 2):
            draw.rectangle([i, j, i + step, j + step], fill="black")
    # Corner squares
    draw.rectangle([x + 3, y + 3, x + 26, y + 26], outline="black", width=3)
    draw.rectangle([x + 9, y + 9, x + 20, y + 20], fill="black")
    draw.rectangle([x + size - 26, y + 3, x + size - 3, y + 26], outline="black", width=3)
    draw.rectangle([x + size - 20, y + 9, x + size - 9, y + 20], fill="black")
    draw.rectangle([x + 3, y + size - 26, x + 26, y + size - 3], outline="black", width=3)
    draw.rectangle([x + 9, y + size - 20, x + 20, y + size - 9], fill="black")


def generate_exact_card_pdf(data: dict) -> bytes:
    """Original RC card template jaisa exact layout PDF render karta hai"""
    width = 1750
    height = 680
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    card_bg = "#CEE6F3"
    border_col = "#4C7C97"
    text_dark = "#111111"

    try:
        f_title = ImageFont.truetype("arialbd.ttf", 22)
        f_bold = ImageFont.truetype("arialbd.ttf", 18)
        f_reg = ImageFont.truetype("arial.ttf", 17)
        f_small_bold = ImageFont.truetype("arialbd.ttf", 14)
        f_small = ImageFont.truetype("arial.ttf", 14)
    except Exception:
        f_title = f_bold = f_reg = f_small_bold = f_small = ImageFont.load_default()

    # --- FRONT CARD ---
    c1_x1, c1_y1, c1_x2, c1_y2 = 40, 30, 840, 630
    draw.rounded_rectangle([c1_x1, c1_y1, c1_x2, c1_y2], radius=20, fill=card_bg, outline=border_col, width=3)

    state_txt = data.get("rtoData", {}).get("statename", "GUJARAT").upper()
    draw.text((c1_x1 + 130, c1_y1 + 25), "Indian Union Vehicle Registration Certificate", fill=text_dark, font=f_title)
    draw.text((c1_x1 + 130, c1_y1 + 55), f"Issued by Government of {state_txt}", fill=text_dark, font=f_bold)

    # Badges
    draw.ellipse([c1_x2 - 110, c1_y1 + 35, c1_x2 - 62, c1_y1 + 83], fill="#5CD0F0")
    draw.text((c1_x2 - 96, c1_y1 + 48), "NT", fill="black", font=f_bold)
    draw.ellipse([c1_x2 - 55, c1_y1 + 35, c1_x2 - 7, c1_y1 + 83], fill="#E67E22")
    state_short = data.get("regNo", "GJ")[:2]
    draw.text((c1_x2 - 43, c1_y1 + 48), state_short, fill="black", font=f_bold)

    reg_no = data.get("regNo", "")
    reg_dt = format_date_to_card(data.get("regDate", ""))
    val_dt = format_date_to_card(data.get("insuranceUpto", ""))

    draw.text((c1_x1 + 130, c1_y1 + 105), "Regn. No", fill=text_dark, font=f_bold)
    draw.text((c1_x1 + 130, c1_y1 + 132), reg_no, fill=text_dark, font=f_reg)

    draw.text((c1_x1 + 320, c1_y1 + 105), "Date of Regn.", fill=text_dark, font=f_bold)
    draw.text((c1_x1 + 320, c1_y1 + 132), reg_dt, fill=text_dark, font=f_reg)

    draw.text((c1_x1 + 520, c1_y1 + 105), "Regn. Validity", fill=text_dark, font=f_bold)
    draw.text((c1_x1 + 520, c1_y1 + 132), val_dt, fill=text_dark, font=f_reg)

    draw.text((c1_x2 - 130, c1_y1 + 105), "Owner", fill=text_dark, font=f_bold)
    draw.text((c1_x2 - 130, c1_y1 + 130), "Serial", fill=text_dark, font=f_bold)
    draw.ellipse([c1_x2 - 65, c1_y1 + 120, c1_x2 - 30, c1_y1 + 155], outline="black", width=2)
    draw.text((c1_x2 - 53, c1_y1 + 126), "1", fill="black", font=f_bold)

    draw.text((c1_x1 + 130, c1_y1 + 175), "Chassis Number", fill=text_dark, font=f_bold)
    draw.text((c1_x1 + 130, c1_y1 + 202), data.get("chassis", ""), fill=text_dark, font=f_reg)

    draw.text((c1_x1 + 130, c1_y1 + 245), "Engine / Motor Number", fill=text_dark, font=f_bold)
    draw.text((c1_x1 + 130, c1_y1 + 272), data.get("engine", ""), fill=text_dark, font=f_reg)

    draw.text((c1_x1 + 130, c1_y1 + 315), "Owner Name", fill=text_dark, font=f_bold)
    draw.text((c1_x1 + 130, c1_y1 + 342), data.get("owner", ""), fill=text_dark, font=f_reg)

    draw.text((c1_x1 + 130, c1_y1 + 385), "Son / Daughter / Wife of (In case of Individual Owner)", fill=text_dark, font=f_bold)
    draw.text((c1_x1 + 130, c1_y1 + 412), data.get("ownerFatherName", ""), fill=text_dark, font=f_reg)

    draw.text((c1_x1 + 130, c1_y1 + 455), "Address", fill=text_dark, font=f_bold)
    full_addr = (data.get("presentAddress") or data.get("permAddress") or "").strip()
    draw.text((c1_x1 + 130, c1_y1 + 482), full_addr[:60], fill=text_dark, font=f_reg)
    if len(full_addr) > 60:
        draw.text((c1_x1 + 130, c1_y1 + 508), full_addr[60:120], fill=text_dark, font=f_reg)

    draw.text((c1_x1 + 20, c1_y1 + 360), "Fuel", fill=text_dark, font=f_small_bold)
    draw.text((c1_x1 + 20, c1_y1 + 385), data.get("fuelType", "PETROL"), fill=text_dark, font=f_small)

    draw.text((c1_x1 + 20, c1_y1 + 450), "Emission Norms", fill=text_dark, font=f_small_bold)
    draw.text((c1_x1 + 20, c1_y1 + 475), "BHARAT STAGE IV", fill=text_dark, font=f_small)

    # --- BACK CARD ---
    c2_x1, c2_y1, c2_x2, c2_y2 = 890, 30, 1690, 630
    draw.rounded_rectangle([c2_x1, c2_y1, c2_x2, c2_y2], radius=20, fill=card_bg, outline=border_col, width=3)

    draw.ellipse([c2_x1 + 20, c2_y1 + 35, c2_x1 + 68, c2_y1 + 83], fill="#5CD0F0")
    draw.text((c2_x1 + 34, c2_y1 + 48), "NT", fill="black", font=f_bold)
    draw.ellipse([c2_x1 + 75, c2_y1 + 35, c2_x1 + 123, c2_y1 + 83], fill="#E67E22")
    draw.text((c2_x1 + 87, c2_y1 + 48), state_short, fill="black", font=f_bold)

    v_class = data.get("vehicleClass", "M-Cycle/Scooter(2WN)")
    draw.text((c2_x1 + 145, c2_y1 + 50), f"VEHICLE CLASS : {v_class}", fill=text_dark, font=f_title)

    draw.text((c2_x1 + 25, c2_y1 + 105), "Regn. Number", fill=text_dark, font=f_bold)
    draw.text((c2_x1 + 25, c2_y1 + 132), reg_no, fill=text_dark, font=f_reg)

    draw_qr_matrix(draw, c2_x1 + 25, c2_y1 + 165, 140)

    specs_x = c2_x1 + 210
    draw.text((specs_x, c2_y1 + 105), "Maker:", fill=text_dark, font=f_bold)
    draw.text((specs_x + 100, c2_y1 + 105), data.get("manufacturer", ""), fill=text_dark, font=f_reg)

    draw.text((specs_x, c2_y1 + 165), "Model:", fill=text_dark, font=f_bold)
    draw.text((specs_x + 100, c2_y1 + 165), data.get("vehicle", ""), fill=text_dark, font=f_reg)

    draw.text((specs_x, c2_y1 + 225), "Color:", fill=text_dark, font=f_bold)
    draw.text((specs_x + 100, c2_y1 + 225), data.get("color", "WHITE"), fill=text_dark, font=f_reg)
    draw.text((specs_x + 320, c2_y1 + 225), "/ Body Type:  SALOON", fill=text_dark, font=f_bold)

    draw.text((specs_x, c2_y1 + 285), "Seating (in all) Capacity", fill=text_dark, font=f_bold)
    draw.text((specs_x, c2_y1 + 312), data.get("seatCapacity", "2"), fill=text_dark, font=f_reg)

    draw.text((specs_x, c2_y1 + 365), "Unladen Weight (Kg)", fill=text_dark, font=f_bold)
    draw.text((specs_x, c2_y1 + 392), data.get("unladenWeight", "110"), fill=text_dark, font=f_reg)

    draw.text((c2_x1 + 25, c2_y1 + 455), "Month - Year of Mfg.", fill=text_dark, font=f_small_bold)
    draw.text((c2_x1 + 25, c2_y1 + 480), data.get("manufacturerMonthYear", "3/2017"), fill=text_dark, font=f_small)

    draw.text((c2_x1 + 220, c2_y1 + 455), "Cubic Cap.", fill=text_dark, font=f_small_bold)
    draw.text((c2_x1 + 220, c2_y1 + 480), f"{data.get('cubicCapacity', '124')}", fill=text_dark, font=f_small)

    draw.text((c2_x1 + 370, c2_y1 + 455), "No of Cylinders : 1", fill=text_dark, font=f_small_bold)
    draw.text((c2_x1 + 520, c2_y1 + 455), "Financier", fill=text_dark, font=f_small_bold)

    draw.text((c2_x1 + 480, c2_y1 + 515), "Registration Authority", fill=text_dark, font=f_small_bold)
    draw.text((c2_x1 + 480, c2_y1 + 540), data.get("regAuthority", ""), fill=text_dark, font=f_small)

    draw.text((c2_x2 - 35, c2_y1 + 280), "Form : 23A", fill=text_dark, font=f_small_bold)

    pdf_out = io.BytesIO()
    img.save(pdf_out, format="PDF", resolution=150.0)
    pdf_out.seek(0)
    return pdf_out.getvalue()


# --- 1. DIRECT PDF DOWNLOAD ROUTE ---
@app.route("/rcdownload")
def rc_pdf_download():
    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({"error": "vehicle parameter required"}), 400

    try:
        data = fetch_rc_data(vehicle)
        pdf_bytes = generate_exact_card_pdf(data)

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"RC_{vehicle}.pdf"
        )
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# --- 2. EXACT JSON RESPONSE AS REQUESTED ---
@app.route("/rc")
def rc_json():
    start_time = time.time()
    current_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    vehicle = request.args.get("vehicle", "").strip().upper()
    if not vehicle:
        return jsonify({
            "execution_time": f"{round(time.time() - start_time, 3)}s",
            "message": "vehicle parameter required",
            "pdf": None,
            "rcno": vehicle,
            "status": "error",
            "timestamp": current_timestamp
        }), 400

    try:
        data = fetch_rc_data(vehicle)
        pdf_bytes = generate_exact_card_pdf(data)
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

        return jsonify({
            "execution_time": f"{round(time.time() - start_time, 3)}s",
            "message": "RC PDF fetched successfully",
            "pdf": pdf_base64,
            "rcno": vehicle,
            "status": "success",
            "timestamp": current_timestamp
        }), 200

    except Exception as exc:
        return jsonify({
            "execution_time": f"{round(time.time() - start_time, 3)}s",
            "message": str(exc),
            "pdf": None,
            "rcno": vehicle,
            "status": "error",
            "timestamp": current_timestamp
        }), 500


@app.route("/")
def index():
    return (
        "<h2>RC Card Generator</h2>"
        "<ul>"
        "<li><code>/rcdownload?vehicle=GJ05PB4974</code> — Direct PDF Download</li>"
        "<li><code>/rc?vehicle=GJ05PB4974</code> — JSON with Base64 PDF</li>"
        "</ul>"
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

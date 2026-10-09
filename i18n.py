"""Tiny UI translation: English is the source text, Thai is looked up.
Switching language takes effect after restarting the program."""

LANG = "en"
LANGUAGES = {"en": "English", "th": "ไทย"}

TH = {
    # header / menus
    "New window": "หน้าต่างใหม่", "Tests": "ทดสอบ", "Settings": "ตั้งค่า", "Help": "ช่วยเหลือ",
    "RTSP Video": "วิดีโอ RTSP", "Theme": "ธีม", "●  Disconnected": "●  ไม่ได้เชื่อมต่อ",
    "Check for updates": "ตรวจหาอัปเดต", "Report a problem…": "แจ้งปัญหา…",
    "Open log folder": "เปิดโฟลเดอร์ log", "Open settings folder": "เปิดโฟลเดอร์ค่าตั้งค่า",
    "Third-party licences": "สัญญาอนุญาตของไลบรารี", "About SuperTerm": "เกี่ยวกับ SuperTerm",
    "Send file (XMODEM / YMODEM)…": "ส่งไฟล์ (XMODEM / YMODEM)…",
    # connection
    "CONNECTION": "การเชื่อมต่อ", "one connection at a time": "เชื่อมต่อได้ทีละหนึ่ง",
    "▶  Connect": "▶  เชื่อมต่อ", "■  Disconnect": "■  ตัดการเชื่อมต่อ",
    "COM Port": "พอร์ต COM", "Refresh ports": "รีเฟรชพอร์ต", "Auto-reconnect": "ต่อใหม่อัตโนมัติ",
    "Reconnect by itself when the USB-UART is unplugged / the board reboots":
        "ต่อใหม่เองเมื่อถอดสาย USB-UART หรือบอร์ดรีบูต",
    "Port": "พอร์ต", "User": "ผู้ใช้", "Password": "รหัสผ่าน", "every": "ทุก", "s": "วิ",
    "Ping first · auto-reconnect": "Ping ก่อน · ต่อใหม่อัตโนมัติ",
    "Saved passwords…": "รหัสผ่านที่บันทึกไว้…", "Profile…": "โปรไฟล์…",
    "Save these settings as a profile": "บันทึกค่าการเชื่อมต่อนี้เป็นโปรไฟล์",
    "Delete the selected profile": "ลบโปรไฟล์ที่เลือก", "Profile name:": "ชื่อโปรไฟล์:",
    "Save profile": "บันทึกโปรไฟล์", "Delete profile": "ลบโปรไฟล์",
    # quick commands
    "QUICK CMD": "คำสั่งด่วน", "＋ Tab": "＋ แท็บ", "＋ Command": "＋ คำสั่ง",
    "Import": "นำเข้า", "Export": "ส่งออก",
    "From the old program (quick_commands.json)…": "จากโปรแกรมเก่า (quick_commands.json)…",
    "From an exported file…": "จากไฟล์ที่ส่งออกไว้…",
    "No quick commands yet — press ＋ Command, or Import from the old program.":
        "ยังไม่มีคำสั่งด่วน — กด ＋ คำสั่ง หรือนำเข้าจากโปรแกรมเก่า",
    "This tab is empty — press ＋ Command to add one.": "แท็บนี้ยังว่าง — กด ＋ คำสั่ง เพื่อเพิ่ม",
    # send
    "SEND": "ส่ง", "▶  Send": "▶  ส่ง",
    "Type a command and press Enter  (↑ / ↓ = history)": "พิมพ์คำสั่งแล้วกด Enter  (↑ / ↓ = คำสั่งก่อนหน้า)",
    "Type hex bytes, e.g.  AA 55 01 0D": "พิมพ์ไบต์แบบ hex เช่น  AA 55 01 0D",
    "Send the text as hex bytes (no line ending is added)": "ส่งเป็นไบต์ hex (ไม่เติมตัวขึ้นบรรทัดใหม่)",
    # output
    "OUTPUT": "ผลลัพธ์", "Terminal": "เทอร์มินัล", "Log": "Log", "Hex": "Hex",
    "Enter sends": "Enter ส่ง", "Local echo": "แสดงที่พิมพ์เอง",
    "select = copy · right-click = paste": "ลากคลุม = คัดลอก · คลิกขวา = วาง",
    "Filter": "กรอง", "show only lines containing…": "แสดงเฉพาะบรรทัดที่มีคำ…",
    "Auto Scroll": "เลื่อนอัตโนมัติ", "Save": "บันทึก", "Clear": "ล้าง",
    "Raw bytes received (RX) and sent (TX)": "ไบต์ดิบที่รับ (RX) และส่ง (TX)",
    "Auto-save log": "บันทึก log อัตโนมัติ",
    # settings dialog
    "Logging": "การบันทึก log", "Save every connection to a log file automatically":
        "บันทึกทุกการเชื่อมต่อลงไฟล์ log อัตโนมัติ",
    "Log folder": "โฟลเดอร์ log", "Browse…": "เลือก…", "Open": "เปิด",
    "Alerts & highlight": "แจ้งเตือนและไฮไลต์", "Beep when a FAIL / error line arrives":
        "ส่งเสียงเมื่อเจอบรรทัด FAIL / error",
    "Extra highlight words (line gets this colour)": "คำไฮไลต์เพิ่มเติม (ทั้งบรรทัดเป็นสีนี้)",
    "Text": "ข้อความ", "Colour": "สี", "Regex": "Regex", "Add": "เพิ่ม", "Remove": "ลบ",
    "Updates": "การอัปเดต", "Channel": "ช่องทาง", "Stable": "ปกติ (Stable)",
    "Beta (try new versions first)": "Beta (ได้เวอร์ชันใหม่ก่อน)",
    "Check automatically when the program starts": "ตรวจอัตโนมัติตอนเปิดโปรแกรม",
    "Language": "ภาษา", "Restart SuperTerm to change the language.": "ปิดแล้วเปิด SuperTerm ใหม่เพื่อเปลี่ยนภาษา",
    "Cancel": "ยกเลิก", "OK": "ตกลง", "Close": "ปิด",
    # test runner
    "Test sequences": "ลำดับทดสอบ", "Sequence": "ลำดับ", "New": "ใหม่", "Rename": "เปลี่ยนชื่อ",
    "Delete": "ลบ", "Send (command)": "ส่ง (คำสั่ง)", "Expect (text or re:regex)": "รอข้อความ (หรือ re:regex)",
    "Timeout s": "หมดเวลา (วิ)", "If fail": "ถ้าไม่ผ่าน", "stop": "หยุด", "continue": "ทำต่อ",
    "＋ Step": "＋ ขั้นตอน", "Remove step": "ลบขั้นตอน", "Up": "ขึ้น", "Down": "ลง",
    "Unit / SN": "เครื่อง / SN", "▶  Run": "▶  เริ่ม", "■  Stop": "■  หยุด",
    "Save results to CSV automatically": "บันทึกผลลง CSV อัตโนมัติ",
    "Result": "ผล", "Step": "ขั้น", "Matched line / reason": "บรรทัดที่เจอ / เหตุผล", "Time s": "เวลา (วิ)",
    "Connect first, then run the sequence.": "เชื่อมต่อก่อน แล้วค่อยเริ่มลำดับทดสอบ",
    # transfer
    "Send file": "ส่งไฟล์", "Protocol": "โปรโตคอล", "File": "ไฟล์", "Start": "เริ่ม",
    "Start the receiver on the device first (U-Boot: loady / loadx), then press Start.":
        "สั่งฝั่งบอร์ดให้รอรับก่อน (U-Boot: loady / loadx) แล้วกดเริ่ม",
    # added in 1.1
    "Tools": "เครื่องมือ", "Connecting…": "กำลังเชื่อมต่อ…",
    "Not connected — press Connect first": "ยังไม่ได้เชื่อมต่อ — กดเชื่อมต่อก่อน",
    "Button label": "ชื่อปุ่ม", "Command": "คำสั่ง",
    "Use  |  to send several commands in sequence.": "ใช้  |  คั่นเพื่อส่งหลายคำสั่งต่อกัน",
    "Both label and command are required.": "ต้องกรอกทั้งชื่อปุ่มและคำสั่ง",
    "Group": "กลุ่ม", "Tab": "แท็บ", "＋ Group": "＋ กลุ่ม",
    "New group (a big set of tabs)": "กลุ่มใหม่ (ชุดใหญ่ที่มีหลายแท็บ)",
    "New tab inside this group": "แท็บใหม่ในกลุ่มนี้", "Line end": "ปิดท้าย",
    "Added after every quick command / test step": "ต่อท้ายทุกคำสั่งด่วน / ขั้นทดสอบ",
    "✏  Edit": "✏  แก้ไข", "Edit": "แก้ไข",
    "Edit mode: click a group, tab or command to change it": "โหมดแก้ไข: คลิกกลุ่ม แท็บ หรือคำสั่งเพื่อแก้",
    "Edit mode — click a group, tab or command to rename, move or delete it":
        "โหมดแก้ไข — คลิกกลุ่ม แท็บ หรือคำสั่ง เพื่อเปลี่ยนชื่อ ย้าย หรือลบ",
    "Send file…": "ส่งไฟล์…", "Send serial BREAK (Tera Term: Alt+B)": "ส่งสัญญาณ BREAK (Tera Term: Alt+B)",
    "Type directly like Tera Term — every key goes to the device": "พิมพ์ตรงแบบ Tera Term — ทุกปุ่มส่งไปที่บอร์ด",
    "Line log with filter and colours": "log ทีละบรรทัด มีตัวกรองและสี",
    "Bring quick commands in from the old program or from an exported file":
        "นำคำสั่งด่วนเข้ามาจากโปรแกรมเก่าหรือจากไฟล์ที่ส่งออกไว้",
    "Save ALL quick commands (every protocol) to a file — e.g. to copy to another PC":
        "บันทึกคำสั่งด่วนทั้งหมดลงไฟล์ — เช่นเพื่อย้ายไปเครื่องอื่น",
    "Each step sends a command and waits for the expected text (e.g. OK) within the timeout → PASS, otherwise FAIL. Press New to start.":
        "แต่ละขั้นจะส่งคำสั่งแล้วรอข้อความที่คาดไว้ (เช่น OK) ภายในเวลาที่กำหนด → ผ่าน ถ้าไม่เจอ → ไม่ผ่าน  กด ใหม่ เพื่อเริ่ม",
}


def set_lang(code):
    global LANG
    LANG = code if code in LANGUAGES else "en"


def T(text):
    if LANG == "th":
        return TH.get(text, text)
    return text

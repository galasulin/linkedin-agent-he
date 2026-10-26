#!/usr/bin/env python3
"""he_check.py - Hebrew LinkedIn humanizer + 5-check detector (single file, no deps).

  python3 he_check.py draft.txt            # score only
  python3 he_check.py draft.txt --fix      # clean invisible chars + typography, write draft.clean.txt, score both
  python3 he_check.py draft.txt --json

Auto-fixed: invisible/format chars, em/en dash, curly quotes, ellipsis, bullets.
Flagged only (Hebrew morphology makes regex rewrites unsafe): stock phrases, structural tells.
Local heuristics, NOT GPTZero/Originality. Never claim "undetectable".
"""
import json, re, statistics, sys, unicodedata

HEB = "א-ת"
PFX = rf"(?<![{HEB}])(?:[ובכלשמה]{{0,2}})"   # Hebrew one-letter prefixes: ו ה ב כ ל ש מ

SLOP = [  # (phrase, why/fix)
 ("בעולם של היום", "פתיחה של AI. מחק ותתחיל מהנקודה"), ("בימינו", "פתיחה של AI"), ("בימנו", "פתיחה של AI"),
 ("בעידן הדיגיטלי", "פתיחה של AI"), ("בתקופה המודרנית", "פתיחה של AI"), ("כיום יותר מתמיד", "פתיחה של AI"),
 ("בעולם המשתנה", "פתיחה של AI"), ("בעולם הדינמי", "פתיחה של AI"),
 ("חשוב לציין", "מחק. אם זה חשוב, שים את זה ראשון"), ("יש לציין", "מחק"), ("ראוי להדגיש", "מחק"),
 ("כדאי לציין", "מחק"), ("חשוב לזכור", "מחק"), ("חשוב להבין", "מחק"),
 ("יתר על כן", "פורמלי מדי. 'וגם' / 'מה גם ש'"), ("לאור זאת", "פורמלי. 'אז'"), ("בהתאם לכך", "פורמלי. 'אז'"),
 ("כפי שניתן לראות", "מחק"), ("מכאן שניתן להסיק", "מחק"), ("ניתן לראות", "סביל. מי רואה? 'ראיתי'"),
 ("ניתן להסיק", "סביל"), ("ניתן לומר", "סביל"), ("נמצא כי", "סביל. מי מצא?"), ("נראה כי", "סביל"),
 ("כמו כן", "מנייה מכנית"), ("בנוסף לכך", "מנייה מכנית"), ("ראשית", "מנייה מכנית"), ("שנית", "מנייה מכנית"),
 ("שאלה מצוינת", "פתיחה מתחנפת. מחק"), ("בשמחה אסייע", "צ'טבוט. מחק"),
 ("לסיכום", "סיכום מיותר. פוסט נגמר כשהוא נגמר"), ("בסיכומו של דבר", "סיכום מיותר"),
 ("לאור האמור לעיל", "בירוקרטי"), ("מכל האמור", "בירוקרטי"), ("כפי שראינו", "סיכום מיותר"),
 ("שורה תחתונה", "קלישאה"), ("משנה משחק", "קלישאה מתורגמת (game changer)"), ("משנה את כללי המשחק", "קלישאה"),
 ("פורץ דרך", "סופרלטיב ריק"), ("מהפכני", "סופרלטיב ריק"), ("חסר תקדים", "סופרלטיב ריק"),
 ("בואו נצלול", "תרגום של let's dive in"), ("נצלול לעומק", "תרגום של dive deep"), ("צלילה לעומק", "תרגום"),
 ("בואו נדבר על", "פתיחה מבוימת"), ("הנה הדבר", "תרגום של here's the thing"),
 ("המסע שלי", "קלישאת 'journey'"), ("ממלא תפקיד מכריע", "AI. 'חשוב ל-' או מספר"),
 ("תפקיד מרכזי", "AI"), ("חשיבות עליונה", "AI"), ("באופן משמעותי", "תן מספר במקום"),
 ("בצורה חלקה", "תרגום של seamless"), ("למנף", "תרגום של leverage. 'להשתמש ב'"), ("מינוף", "leverage"),
 ("סינרגיה", "ז'רגון"), ("אקוסיסטם", "ז'רגון"), ("פתרון הוליסטי", "ז'רגון"), ("ערך מוסף", "קלישאה"),
 ("לא פחות ממדהים", "הגזמה"), ("תנו לזה לחלחל", "תרגום של let that sink in"), ("קראו שוב", "פיתיון"),
]

STRUCT = [  # (id, regex, fix)
 ("לא-רק-אלא", r"לא רק[^.!?\n]{2,80}אלא (?:גם)?", "הגד את הדבר האחד. מחק את חצי ההקמה"),
 ("זה-לא-X-זה-Y", r"(?:זה|זו|הוא|היא) לא (?:רק |על )?[^.!?\n]{2,50}[,.]\s*(?:זה|זו|הוא|היא) ", "התחל ב-Y. ההיפוך הוא הסימן"),
 ("שורת-חשיפה", r"(?m)^\s*(?:התוצאה|והתוצאה|החלק הכי טוב|והקאץ'|המלכוד|הסוד)\?\s*$", "ענה בתוך המשפט, בלי חשיפה מבוימת"),
 ("הנה-מה-שלמדתי", r"הנה מה ש(?:למדתי|למדנו|גיליתי)", "פשוט תגיד את הלקח"),
 ("שלישייה", rf"[{HEB}\w]+, [{HEB}\w]+ ו-?[{HEB}\w]+\.", "שניים או ארבעה. שלוש זה הקצב של המודל"),
 ("אימוג'י-AI", "[\U0001F680\U0001F525\U0001F4A1✨\U0001F3AF\U0001F447]", "אימוג'י אחד לכל היותר, לא מאלה"),
 ("קיר-האשטגים", r"(?:#\S+[ \t]*){4,}", "עד 3 האשטגים"),
 ("פיתיון-מעורבות", r"(?:מה דעתכם|מסכימים|מי עוד|מה אתם אומרים|תגידו בתגובות)\s*\??\s*$", "שאלה שרק הפוסט הזה יכול לשאול"),
 ("ניקוד", "[ְ-ּׁׂ]", "אין ניקוד בפוסט מקצועי"),
]

PERSON = re.compile(rf"(?<![{HEB}])[ובכלשמה]?(?:אני|אנחנו|שלי|שלנו|לי|לנו|אותי|אותנו|אתה|אתם|את|שלך|שלכם|לך|לכם|עשיתי|הייתי|ראיתי|למדתי|גיליתי|בניתי|החלטתי|ניסיתי)(?![{HEB}])")
COLLOQ = re.compile(rf"(?<![{HEB}])(?:אז|בעצם|תכלס|סתם|נו|וואלה|יאללה|כאילו|פשוט|ממש|בקיצור|אגב|אחי|לא\?)(?![{HEB}])")
NUM = re.compile(r"\d[\d,.:]*%?|₪\d|\$\d")
LATIN = re.compile(r"\b[A-Za-z][A-Za-z0-9.+#-]{1,}\b")   # code-switch: SQL, Windows, VPN...
WORD = re.compile(rf"[{HEB}A-Za-z0-9'\"״׳-]+")
SENT = re.compile(r"[^.!?\n]+[.!?]*")
TYPO = {"—": ", ", "–": "-", "‘": "'", "’": "'", "“": '"', "”": '"', "„": '"', "…": "...", "•": "-", "·": "-", "→": "->"}

clamp = lambda n: max(0.0, min(100.0, n))
def scale(v, human, machine): return clamp((v - machine) / (human - machine) * 100)

def fix(text):
    changes = {}
    inv = sum(1 for c in text if unicodedata.category(c) == "Cf")
    if inv: changes["תווים בלתי נראים"] = inv
    text = "".join(c for c in text if unicodedata.category(c) != "Cf")
    for sp in "    ": text = text.replace(sp, " ")
    for ch, to in TYPO.items():
        n = text.count(ch)
        if not n: continue
        changes[ch] = n
        if ch == "—": text = re.sub(r"\s*—\s*", ", ", text)
        elif ch == "–":
            text = re.sub(r"\s*–\s*(?=\d)", "-", text); text = re.sub(r"\s+–\s+", ", ", text); text = text.replace("–", "-")
        else: text = text.replace(ch, to)
    text = re.sub(r",\s*([,.;:!?])", r"\1", text); text = re.sub(r",[ \t]*\n", "\n", text)
    return text, changes

def slop_hits(text):
    out = []
    for p, why in SLOP:
        n = len(re.findall(PFX + re.escape(p).replace(r"\ ", r"\s+") + rf"(?![{HEB}])", text))
        if n: out.append((p, n, why))
    return out

def struct_hits(text):
    out = []
    for i, rx, f in STRUCT:
        n = len(re.findall(rx, text))
        if n: out.append((i, n, f))
    return out

def score(text):
    words = WORD.findall(text); nw = max(len(words), 1); per100 = 100 / nw
    lens = [len(s.split()) for s in SENT.findall(text) if len(s.split()) >= 2 and not s.strip().startswith("#")]
    if len(lens) >= 4:
        cv = statistics.pstdev(lens) / statistics.mean(lens); b = (scale(cv, .65, .20), f"שונות {cv:.2f} על {len(lens)} משפטים (רצוי 0.55+)")
    else: b = (50.0, "קצר מדי לשיפוט")
    conc = len(NUM.findall(text)) + len(set(LATIN.findall(text)))
    s = (scale(conc * per100, 5.0, 0.5), f"{conc} סממנים קונקרטיים (מספרים/מונחים), {conc*per100:.1f} ל-100 מילים (רצוי 4+)") if nw >= 25 else (50.0, "קצר מדי")
    sh = slop_hits(text); hits = sum(n for _, n, _ in sh)
    sl = (scale(hits * per100, 0.0, 3.0), f"{hits} ביטויים שחוקים" + (" (" + ", ".join(p for p, _, _ in sh[:4]) + ")" if sh else ""))
    inv = sum(1 for c in text if unicodedata.category(c) == "Cf"); em = text.count("—")
    curly = sum(text.count(c) for c in "‘’“”„"); el = text.count("…")
    tot = inv * 4 + em * 2 + curly + el
    fp = (scale(tot * 1000 / max(len(text), 1), 0.0, 12.0), f"{inv} בלתי נראים, {em} קו מפריד ארוך, {curly} מירכאות מסולסלות, {el} שלוש-נקודות")
    st = struct_hits(text); tells = sum(n for _, n, _ in st)
    pers = len(PERSON.findall(text)) * per100; col = len(COLLOQ.findall(text)) * per100
    v = clamp(scale(pers, 6.0, 0.5) * .40 + scale(col, 2.0, 0.0) * .25 + clamp(100 - tells * 22) * .35) if nw >= 25 else 50.0
    vo = (v, f"גוף ראשון/שני {pers:.1f}, שפה מדוברת {col:.1f} ל-100 מילים, {tells} סימני מבנה" + (" [" + ", ".join(i for i, _, _ in st[:4]) + "]" if st else ""))
    res = {"קצב (BURSTINESS)": b, "קונקרטיות": s, "ביטויים שחוקים": sl, "טביעת אצבע": fp, "קול": vo}
    sc = [r[0] for r in res.values()]; overall = statistics.mean(sc) * .6 + min(sc) * .4
    verdict = "PASS" if overall >= 70 and min(sc) >= 55 else ("REVIEW" if overall >= 50 else "FLAGGED")
    return res, overall, verdict, sh, st

def render(label, text):
    res, ov, vd, sh, st = score(text)
    print(f"\n== {label} ==")
    for k, (s, d) in res.items(): print(f"  {k:<18} {'#'*round(s/100*20):<20} {s:5.1f}  {d}")
    print(f"  {'ציון אנושי':<18} {'#'*round(ov/100*20):<20} {ov:5.1f}  {vd}")
    for p, n, w in sh: print(f"  ⚑ '{p}' x{n}: {w}")
    for i, n, f in st: print(f"  ⚑ [{i}] x{n}: {f}")
    return {"label": label, "human_score": round(ov, 1), "verdict": vd,
            "checks": {k: round(v[0], 1) for k, v in res.items()},
            "flags": [p for p, _, _ in sh] + [i for i, _, _ in st]}

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1255
    a = sys.argv[1:]; path = next(x for x in a if not x.startswith("--"))
    text = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
    out = [render("לפני" if "--fix" in a else "טיוטה", text)]
    if "--fix" in a:
        clean, ch = fix(text); dst = (path.rsplit(".", 1)[0] if path != "-" else "draft") + ".clean.txt"
        open(dst, "w", encoding="utf-8").write(clean)
        print("\nתוקן אוטומטית:", ch or "כלום", "->", dst)
        out.append(render("אחרי", clean))
    if "--json" in a: print(json.dumps(out, ensure_ascii=False, indent=1))
    sys.exit(0 if out[-1]["verdict"] == "PASS" else 1)

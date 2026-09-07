"""Constants for the Hebcal integration."""
import json
import os
from datetime import timedelta
from typing import Final

# --- שאיבת הגרסה באופן דינמי מקובץ manifest.json ---
try:
    dir_path = os.path.dirname(os.path.realpath(__file__))
    manifest_path = os.path.join(dir_path, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
        VERSION: Final = manifest_data.get("version", "unknown")
except Exception:
    VERSION: Final = "unknown"

DOMAIN: Final = "hebcal_ui"
UPDATE_INTERVAL: Final = timedelta(minutes=30)  # עדכון כל 30 דקות
FULL_UPDATE_INTERVAL: Final = timedelta(hours=6)  # עדכון מלא כל 6 שעות
IMPORTANT_TIME_BUFFER: Final = timedelta(minutes=30)  # חיץ זמן לאירועים חשובים

# Configuration keys
CONF_HAVDALAH_MINUTES: Final = "havdalah_minutes"
CONF_TIME_BEFORE_CHECK: Final = "time_before_check"
CONF_TIME_AFTER_CHECK: Final = "time_after_check"
CONF_JERUSALEM_CANDLE: Final = "jerusalem_candle"
CONF_TZEIT_HAKOCHAVIM: Final = "tzeit_hakochavim"
CONF_DIASPORA: Final = "diaspora"
CONF_USE_12H_TIME: Final = "use_12h_time"
CONF_OMER_COUNT_TYPE: Final = "omer_count_type"
CONF_LANGUAGE: Final = "language"

# Default values
DEFAULT_HAVDALAH_MINUTES: Final = 42
DEFAULT_TIME_BEFORE_CHECK: Final = 10
DEFAULT_TIME_AFTER_CHECK: Final = 10
DEFAULT_JERUSALEM_CANDLE: Final = False
DEFAULT_TZEIT_HAKOCHAVIM: Final = True
DEFAULT_DIASPORA: Final = False
DEFAULT_OMER_COUNT_TYPE: Final = 0
DEFAULT_USE_12H_TIME: Final = False
DEFAULT_LANGUAGE: Final = "hebrew"

# API URLs
HEBCAL_DATE_URL: Final = (
    "https://www.hebcal.com/hebcal/?v=1&cfg=json&maj=on&min=on&nx=on&mf=on&ss=on&mod=on"
    "&s=on&c=on&o=on&geo=pos&lg={}&start={}&end={}&latitude={}&longitude={}"
    "&tzid={}&b={}&i={}"
)

HEBCAL_DATE_URL_HAVDALAH: Final = (
    "https://www.hebcal.com/hebcal/?v=1&cfg=json&maj=on&min=on&nx=on&mf=on&ss=on&mod=on"
    "&s=on&c=on&o=on&geo=pos&lg={}&start={}&end={}&latitude={}&longitude={}"
    "&tzid={}&m={}&b={}&i={}"
)

# Entity ID mappings - always English for consistency
ENTITY_ID_MAP = {
    "shabbat_in": "shabbat_entry",
    "shabbat_out": "shabbat_exit",
    "yomtov_in": "yom_tov_entry",
    "yomtov_out": "yom_tov_exit",
    "parasha": "torah_portion",
    "yomtov_name": "holiday_name",
    "event_name": "event_name",
    "omer_day": "omer_count",
    "hebrew_date": "hebrew_date",
    "zmanim": "halachic_times",
    "is_shabbat": "is_shabbat",
    "is_yomtov": "is_yom_tov",
}

# Sensor types with English entity IDs
SENSOR_TYPES = {
    "shabbat_in": {
        "entity_id": "shabbat_entry",
        "name": {"hebrew": "כניסת השבת", "english": "Shabbat Entry"},
        "icon": "mdi:candle",
        "device_class": None,
        "unit": None,
    },
    "shabbat_out": {
        "entity_id": "shabbat_exit",
        "name": {"hebrew": "צאת השבת", "english": "Shabbat Exit"},
        "icon": "mdi:exit-to-app",
        "device_class": None,
        "unit": None,
    },
    "yomtov_in": {
        "entity_id": "yom_tov_entry",
        "name": {"hebrew": "כניסת יום טוב", "english": "Yom Tov Entry"},
        "icon": "mdi:candle",
        "device_class": None,
        "unit": None,
    },
    "yomtov_out": {
        "entity_id": "yom_tov_exit",
        "name": {"hebrew": "צאת יום טוב", "english": "Yom Tov Exit"},
        "icon": "mdi:exit-to-app",
        "device_class": None,
        "unit": None,
    },
    "parasha": {
        "entity_id": "torah_portion",
        "name": {"hebrew": "פרשת השבוע", "english": "Torah Portion"},
        "icon": "mdi:book-open-variant",
        "device_class": None,
        "unit": None,
    },
    "yomtov_name": {
        "entity_id": "holiday_name",
        "name": {"hebrew": "יום טוב", "english": "Holiday Name"},
        "icon": "mdi:star-david",
        "device_class": None,
        "unit": None,
    },
    "event_name": {
        "entity_id": "event_name",
        "name": {"hebrew": "אירוע", "english": "Event Name"},
        "icon": "mdi:calendar-today",
        "device_class": None,
        "unit": None,
    },
    "omer_day": {
        "entity_id": "omer_count",
        "name": {"hebrew": "ספירת העומר", "english": "Omer Count"},
        "icon": "mdi:counter",
        "device_class": None,
        "unit": None,
    },
    "hebrew_date": {
        "entity_id": "hebrew_date",
        "name": {"hebrew": "תאריך עברי", "english": "Hebrew Date"},
        "icon": "mdi:calendar-today",
        "device_class": None,
        "unit": None,
    },
    "zmanim": {
        "entity_id": "halachic_times",
        "name": {"hebrew": "זמנים הלכתיים", "english": "Halachic Times"},
        "icon": "mdi:clock-outline",
        "device_class": None,
        "unit": None,
    },
}

BINARY_SENSOR_TYPES = {
    "is_shabbat": {
        "entity_id": "is_shabbat",
        "name": {"hebrew": "האם שבת", "english": "Is Shabbat"},
        "icon": "mdi:candle",
        "device_class": None,
        "unit": None,
    },
    "is_yomtov": {
        "entity_id": "is_yom_tov",
        "name": {"hebrew": "האם יום טוב", "english": "Is Yom Tov"},
        "icon": "mdi:star-david",
        "device_class": None,
        "unit": None,
    },
    "issur_melacha": {
        "entity_id": "issur_melacha",
        "name": {
            "english": "Issur Melacha",
            "hebrew": "איסור מלאכה"
        },
        "icon": "mdi:hand-back-right-off",
        "device_class": None,
        "unit": None,
    },
}

ZMANIM_TRANSLATIONS = {
    "alot_hashachar": {
        "english": "Dawn",
        "hebrew": "עלות השחר",
        "date": None
    },
    "talit_and_tefillin": {
        "english": "Earliest Tallit and Tefillin",
        "hebrew": "זמן טלית ותפילין",
        "date": None
    },
    "netz_hachama": {
        "english": "Sunrise",
        "hebrew": "נץ החמה",
        "date": None
    },
    "sof_zman_shema_mga": {
        "english": "Latest Shema (Magen Avraham)",
        "hebrew": "סוף זמן קריאת שמע (מג\"א)",
        "date": None
    },
    "sof_zman_shema_gra": {
        "english": "Latest Shema (Gra)",
        "hebrew": "סוף זמן קריאת שמע (הגר\"א)",
        "date": None
    },
    "sof_zman_tfilla_mga": {
        "english": "Latest Tefillah (Magen Avraham)",
        "hebrew": "סוף זמן תפילה (מג\"א)",
        "date": None
    },
    "sof_zman_tfilla_gra": {
        "english": "Latest Tefillah (Gra)",
        "hebrew": "סוף זמן תפילה (הגר\"א)",
        "date": None
    },
    "chatzot_hayom": {
        "english": "Midday",
        "hebrew": "חצות היום",
        "date": None
    },
    "mincha_gedola": {
        "english": "Earliest Mincha",
        "hebrew": "מנחה גדולה",
        "date": None
    },
    "mincha_gedola_30min": {
        "english": "Earliest Mincha (30 min after Chatzot)",
        "hebrew": "מנחה גדולה (חצי שעה אחרי חצות)",
        "date": None
    },
    "mincha_ketana": {
        "english": "Mincha Ketana",
        "hebrew": "מנחה קטנה",
        "date": None
    },
    "plag_hamincha": {
        "english": "Plag Hamincha",
        "hebrew": "פלג המנחה",
        "date": None
    },
    "shkia": {
        "english": "Sunset",
        "hebrew": "שקיעה",
        "date": None
    },
    "tset_hakohavim_tsom": {
        "english": "Nightfall (fasts)",
        "hebrew": "צאת הכוכבים (צומות)",
        "date": None
    },
    "tset_hakohavim_shabbat": {
        "english": "Nightfall (Shabbat/Yom Tov)",
        "hebrew": "צאת הכוכבים (שבת/יום טוב)",
        "date": None
    },
    "tset_hakohavim": {
        "english": "Nightfall",
        "hebrew": "צאת הכוכבים",
        "date": None
    },
    "tset_hakohavim_rabeinu_tam": {
        "english": "Nightfall (Rabbeinu Tam)",
        "hebrew": "צאת הכוכבים (רבנו תם)",
        "date": None
    },
    "chatzot_halayla": {
        "english": "Midnight",
        "hebrew": "חצות הלילה",
        "date": None
    }
}

# Language data
LANGUAGE_DATA: Final = {
    "english": {
        "no_info": "No Info",
        "no_event": "No Event",
        "special_shabbat": "Special Shabbat",
        "no_omer": "No Omer Count",
        "zmanim": {
            'chatzotNight': 'Midnight',
            'alotHaShachar': 'Dawn',
            'misheyakir': 'Time for Talit and Tefilin',
            'misheyakirMachmir': 'Time for Talit and Tefilin (Strict)',
            'sunrise': 'Sunrise',
            'sofZmanShma': 'Latest Shema',
            'sofZmanTfilla': 'Latest Shacharit',
            'chatzot': 'Midday',
            'minchaGedola': 'Mincha Gedola',
            'minchaKetana': 'Mincha Ketana',
            'plagHaMincha': 'Plag HaMincha',
            'sunset': 'Sunset',
            'dusk': 'Dusk',
        },
        "code": "s"
    },
    "hebrew": {
        "no_info": "אין מידע",
        "no_event": "אין אירוע",
        "special_shabbat": "שבת מיוחדת",
        "no_omer": "אין ספירת העומר",
        "zmanim": {
            'chatzotNight': 'חצות לילה',
            'alotHaShachar': 'עלות השחר',
            'misheyakir': 'זמן הנחת טלית ותפילין',
            'misheyakirMachmir': 'זמן הנחת טלית ותפילין - מחמיר',
            'sunrise': 'זריחה',
            'sofZmanShma': 'סוף זמן קריאת שמע',
            'sofZmanTfilla': 'סוף זמן תפילת שחרית',
            'chatzot': 'חצות היום',
            'minchaGedola': 'מנחה גדולה',
            'minchaKetana': 'מנחה קטנה',
            'plagHaMincha': 'פלג המנחה',
            'sunset': 'שקיעה',
            'dusk': 'בין הערבים'
        },
        "code": "h"
    }
}

# Hebrew weekdays
HEBREW_WEEKDAY: Final = {
    1: "יום שני, ",
    2: "יום שלישי, ",
    3: "יום רביעי, ",
    4: "יום חמישי, ",
    5: "יום שישי, ",
    6: "יום שבת, ",
    7: "יום ראשון, ",
}

# Omer counting texts
OMER_DAYS: Final = [
    {
        1: "הַאידַּנָא חַד יוֹמָא בְּעֻמרָא",
        2: "הַאידַּנָא תְּרֵין יוֹמֵי בְּעֻמרָא",
        3: "הַאידַּנָא תְּלָתָא יוֹמֵי בְּעֻמרָא",
        4: "הַאידַּנָא אַרבְּעָא יוֹמֵי בְּעֻמרָא",
        5: "הַאידַּנָא חַמשָׁא יוֹמֵי בְּעֻמרָא",
        6: "הַאידַּנָא שִׁתָּא יוֹמֵי בְּעֻמרָא",
        7: "הַאידַּנָא שִׁבעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַד שָׁבוּעָא",
        8: "הַאידַּנָא תְּמָניָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַד שָׁבוּעָא וְחַד יוֹמָא",
        9: "הַאידַּנָא תִּשׁעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַד שָׁבוּעָא וּתרֵין יוֹמֵי",
        10: "הַאידַּנָא עַשׂרָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַד שָׁבוּעָא וּתלָתָא יוֹמֵי",
        11: "הַאידַּנָא חַד עֲשַׂר יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַד שָׁבוּעָא וְאַרבְּעָא יוֹמֵי",
        12: "הַאידַּנָא תְּרֵי עֲשַׂר יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַד שָׁבוּעָא וְחַמשָׁא יוֹמֵי",
        13: "הַאידַּנָא תְּלָת עֲשַׂר יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַד שָׁבוּעָא וְשִׁתָּא יוֹמֵי",
        14: "הַאידַּנָא אַרבַּעַת עֲשַׂר יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּרֵין שָׁבוּעֵי",
        15: "הַאידַּנָא חַמשַׁת עֲשַׂר יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּרֵין שָׁבוּעֵי וְחַד יוֹמָא",
        16: "הַאידַּנָא שִׁתַּת עֲשַׂר יוֹמֵי בְּעֻמרָא, דְאִינּוּן תְּרֵין שָׁבוּעֵי וּתרֵין יוֹמֵי",
        17: "הַאידַּנָא שִׁבעַת עֲשַׂר יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּרֵין שָׁבוּעֵי וּתלָתָא יוֹמֵי",
        18: "הַאידַּנָא תַּמנַת עֲשַׂר יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּרֵין שָׁבוּעֵי וְאַרבְּעָא יוֹמֵי",
        19: "הַאידַּנָא תִּשׁעַת עֲשַׂר יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּרֵין שָׁבוּעֵי וְחַמשָׁא יוֹמֵי",
        20: "הַאידַּנָא עַשׂרִין יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּרֵין שָׁבוּעֵי וְשִׁתָּא יוֹמֵי",
        21: "הַאידַּנָא עַשׂרִין וְחַד יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּלָתָא שָׁבוּעֵי",
        22: "הַאידַּנָא עַשׂרִין וּתרֵין יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּלָתָא שָׁבוּעֵי וְחַד יוֹמָא",
        23: "הַאידַּנָא עַשׂרִין וּתלָתָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּלָתָא שָׁבוּעֵי וּתרֵין יוֹמֵי",
        24: "הַאידַּנָא עַשׂרִין וְאַרבְּעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּלָתָא שָׁבוּעֵי וּתלָתָא יוֹמֵי",
        25: "הַאידַּנָא עַשׂרִין וְחַמשָׁא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּלָתָא שָׁבוּעֵי וְאַרבְּעָא יוֹמֵי",
        26: "הַאידַּנָא עַשׂרִין וְשִׁתָּא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּלָתָא שָׁבוּעֵי וְחַמשָׁא יוֹמֵי",
        27: "הַאידַּנָא עַשׂרִין וְשִׁבעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן תְּלָתָא שָׁבוּעֵי וְשִׁתָּא יוֹמֵי",
        28: "הַאידַּנָא עַשׂרִין וּתמָניָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן אַרבְּעָא שָׁבוּעֵי",
        29: "הַאידַּנָא עַשׂרִין וְתִשׁעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן אַרבְּעָא שָׁבוּעֵי וְחַד יוֹמָא",
        30: "הַאידַּנָא תְּלָתִין יוֹמֵי בְּעֻמרָא, דְּאִנּוּן אַרבְּעָא שָׁבוּעֵי וּתרֵין יוֹמֵי",
        31: "הַאידַּנָא תְּלָתִין וְחַד יוֹמֵי בְּעֻמרָא, דְּאִנּוּן אַרבְּעָא שָׁבוּעֵי וּתלָתָא יוֹמֵי",
        32: "הַאידַּנָא תְּלָתִין וּתרֵין יוֹמֵי בְּעֻמרָא, דְּאִנּוּן אַרבְּעָא שָׁבוּעֵי וְאַרבְּעָא יוֹמֵי",
        33: "הַאידַּנָא תְּלָתִין וּתלָתָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן אַרבְּעָא שָׁבוּעֵי וְחַמשָׁא יוֹמֵי",
        34: "הַאידַּנָא תְּלָתִין וְאַרבְּעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן אַרבְּעָא שָׁבוּעֵי וְשִׁתָּא יוֹמֵי",
        35: "הַאידַּנָא תְּלָתִין וְחַמשָׁא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַמשָׁא שָׁבוּעֵי",
        36: "הַאידַּנָא תְּלָתִין וְשִׁתָּא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַמשָׁא שָׁבוּעֵי וְחַד יוֹמָא",
        37: "הַאידַּנָא תְּלָתִין וְשִׁבעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַמשָׁא שָׁבוּעֵי וּתרֵין יוֹמֵי",
        38: "הַאידַּנָא תְּלָתִין וּתמָניָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַמשָׁא שָׁבוּעֵי וּתלָתָא יוֹמֵי",
        39: "הַאידַּנָא תְּלָתִין וְתִשׁעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַמשָׁא שָׁבוּעֵי וְאַרבְּעָא יוֹמֵי",
        40: "הַאידַּנָא אַרבְּעִין יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַמשָׁא שָׁבוּעֵי וְחַמשָׁא יוֹמֵי",
        41: "הַאידַּנָא אַרבְּעִין וְחַד יוֹמֵי בְּעֻמרָא, דְּאִנּוּן חַמשָׁא שָׁבוּעֵי וְשִׁתָּא יוֹמֵי",
        42: "הַאידַּנָא אַרבְּעִין וּתרֵין יוֹמֵי בְּעֻמרָא, דְּאִנּוּן שִׁתָּא שָׁבוּעֵי",
        43: "הַאידַּנָא אַרבְּעִין וּתלָתָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן שִׁתָּא שָׁבוּעֵי וְחַד יוֹמָא",
        44: "הַאידַּנָא אַרבְּעִין וְאַרבְּעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן שִׁתָּא שָׁבוּעֵי וּתרֵין יוֹמֵי",
        45: "הַאידַּנָא אַרבְּעִין וְחַמשָׁא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן שִׁתָּא שָׁבוּעֵי וּתלָתָא יוֹמֵי",
        46: "הַאידַּנָא אַרבְּעִין וְשִׁתָּא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן שִׁתָּא שָׁבוּעֵי וְאַרבְּעָא יוֹמֵי",
        47: "הַאידַּנָא אַרבְּעִין וְשִׁבעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן שִׁתָּא שָׁבוּעֵי וְחַמשָׁא יוֹמֵי",
        48: "הַאידַּנָא אַרבְּעִין וּתמָניָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן שִׁתָּא שָׁבוּעֵי וְשִׁתָּא יוֹמֵי",
        49: "הַאידַּנָא אַרבְּעִין וְתִשׁעָא יוֹמֵי בְּעֻמרָא, דְּאִנּוּן שִׁבעָא שָׁבוּעֵי שַׁלמֵי"
    },
    {
        1: "הַיּוֹם יוֹם אֶחָד לָעֽוֹמֶר",
        2: "הַיוֹם שְׁנֵי יָמִים לָעֽוֹמֶר",
        3: "הַיוֹם שְׁלֹשָׁה יָמִים לָעֽוֹמֶר",
        4: "הַיוֹם אַרְבָּעָה יָמִים לָעֽוֹמֶר",
        5: "הַיוֹם חֲמִשָּׁה יָמִים לָעֽוֹמֶר",
        6: "הַיוֹם שִׁשָׁה יָמִים לָעֽוֹמֶר",
        7: "הַיוֹם שִׁבְעָה יָמִים שֶׁהֵם שָׁבֽוּעַ אֶחָד לָעֽוֹמֶר",
        8: "הַיוֹם שְׁמוֹנָה יָמִים שֶׁהֵם שָׁבֽוּעַ אֶחָד וְיוֹם אֶחָד לָעֽוֹמֶר",
        9: "הַיוֹם תִּשְׁעָה יָמִים שֶׁהֵם שָׁבֽוּעַ אֶחָד וּשְׁנֵי יָמִים לָעֽוֹמֶר",
        10: "הַיוֹם עֲשָׂרָה יָמִים שֶׁהֵם שָׁבֽוּעַ אֶחָד וּשְׁלֹשָׁה יָמִים לָעֽוֹמֶר",
        11: "הַיוֹם אַחַד עָשָׂר יוֹם שֶׁהֵם שָׁבֽוּעַ אֶחָד וְאַרְבָּעָה יָמִים לָעֽוֹמֶר",
        12: "הַיוֹם שְׁנֵים עָשָׂר יוֹם שֶׁהֵם שָׁבֽוּעַ אֶחָד וַחֲמִשָׁה יָמִים לָעֽוֹמֶר",
        13: "הַיוֹם שְׁלֹשָׁה עָשָׂר יוֹם שֶׁהֵם שָׁבֽוּעַ אֶחָד וְשִׁשָׁה יָמִים לָעֽוֹמֶר",
        14: "הַיוֹם אַרְבָּעָה עָשָׂר יוֹם שֶׁהֵם שְׁנֵי שָׁבוּעוֹת לָעֽוֹמֶר",
        15: "הַיוֹם חֲמִשָׁה עָשָׂר יוֹם שֶׁהֵם שְׁנֵי שָׁבוּעוֹת וְיוֹם אֶחָד לָעֽוֹמֶר",
        16: "הַיוֹם שִׁשָׁה עָשָׂר יוֹם שֶׁהֵם שְׁנֵי שָׁבוּעוֹת וּשְׁנֵי יָמִים לָעֽוֹמֶר",
        17: "הַיוֹם שִׁבְעָה עָשָׂר יוֹם שֶׁהֵם שְׁנֵי שָׁבוּעוֹת וּשְׁלֹשָׁה יָמִים לָעֽוֹמֶר",
        18: "הַיוֹם שְׁמוֹנָה עָשָׂר יוֹם שֶׁהֵם שְׁנֵי שָׁבוּעוֹת וְאַרְבָּעָה יָמִים לָעֽוֹמֶר",
        19: "הַיוֹם תִּשְׁעָה עָשָׂר יוֹם שֶׁהֵם שְׁנֵי שָׁבוּעוֹת וַחֲמִשָׁה יָמִים לָעֽוֹמֶר",
        20: "הַיוֹם עֶשְׂרִים יוֹם שֶׁהֵם שְׁנֵי שָׁבוּעוֹת וְשִׁשָׁה יָמִים לָעֽוֹמֶר",
        21: "הַיוֹם אֶחָד וְעֶשְׂרִים יוֹם שֶׁהֵם שְׁלֹשָׁה שָׁבוּעוֹת לָעֽוֹמֶר",
        22: "הַיוֹם שְׁנַֽיִם וְעֶשְׂרִים יוֹם שֶׁהֵם שְׁלֹשָׁה שָׁבוּעוֹת וְיוֹם אֶחָד לָעֽוֹמֶר",
        23: "הַיוֹם שְׁלֹשָׁה וְעֶשְׂרִים יוֹם שֶׁהֵם שְׁלֹשָׁה שָׁבוּעוֹת וּשְׁנֵי יָמִים לָעֽוֹמֶר",
        24: "הַיוֹם אַרְבָּעָה וְעֶשְׂרִים יוֹם שֶׁהֵם שְׁלֹשָׁה שָׁבוּעוֹת וּשְׁלֹשָׁה יָמִים לָעֽוֹמֶר",
        25: "הַיוֹם חֲמִשָׁה וְעֶשְׂרִים יוֹם שֶׁהֵם שְׁלֹשָׁה שָׁבוּעוֹת וְאַרְבָּעָה יָמִים לָעֽוֹמֶר",
        26: "הַיוֹם שִׁשָׁה וְעֶשְׂרִים יוֹם שֶׁהֵם שְׁלֹשָׁה שָׁבוּעוֹת וַחֲמִשָׁה יָמִים לָעֽוֹמֶר",
        27: "הַיוֹם שִׁבְעָה וְעֶשְׂרִים יוֹם שֶׁהֵם שְׁלֹשָׁה שָׁבוּעוֹת וְשִׁשָׁה יָמִים לָעֽוֹמֶר",
        28: "הַיוֹם שְׁמוֹנָה וְעֶשְׂרִים יוֹם שֶׁהֵם אַרְבָּעָה שָׁבוּעוֹת לָעֽוֹמֶר",
        29: "הַיוֹם תִּשְׁעָה וְעֶשְׂרִים יוֹם שֶׁהֵם אַרְבָּעָה שָׁבוּעוֹת וְיוֹם אֶחָד לָעֽוֹמֶר",
        30: "הַיוֹם שְׁלֹשִׁים יוֹם שֶׁהֵם אַרְבָּעָה שָׁבוּעוֹת וּשְׁנֵי יָמִים לָעֽוֹמֶר",
        31: "הַיוֹם אֶחָד וּשְׁלֹשִׁים יוֹם שֶׁהֵם אַרְבָּעָה שָׁבוּעוֹת וּשְׁלֹשָׁה יָמִים לָעֽוֹמֶר",
        32: "הַיוֹם שְׁנַֽיִם וּשְׁלֹשִׁים יוֹם שֶׁהֵם אַרְבָּעָה שָׁבוּעוֹת וְאַרְבָּעָה יָמִים לָעֽוֹמֶר",
        33: "הַיוֹם שְׁלֹשָׁה וּשְׁלֹשִׁים יוֹם שֶׁהֵם אַרְבָּעָה שָׁבוּעוֹת וַחֲמִשָׁה יָמִים לָעֽוֹמֶר",
        34: "הַיוֹם אַרְבָּעָה וּשְׁלֹשִׁים יוֹם שֶׁהֵם אַרְבָּעָה שָׁבוּעוֹת וְשִׁשָׁה יָמִים לָעֽוֹמֶר",
        35: "הַיוֹם חֲמִשָׁה וּשְׁלֹשִׁים יוֹם שֶׁהֵם חֲמִשָׁה שָׁבוּעוֹת לָעֽוֹמֶר",
        36: "הַיוֹם שִׁשָׁה וּשְׁלֹשִׁים יוֹם שֶׁהֵם חֲמִשָׁה שָׁבוּעוֹת וְיוֹם אֶחָד לָעֽוֹמֶר",
        37: "הַיוֹם שִׁבְעָה וּשְׁלֹשִׁים יוֹם שֶׁהֵם חֲמִשָׁה שָׁבוּעוֹת וּשְׁנֵי יָמִים לָעֽוֹמֶר",
        38: "הַיוֹם שְׁמוֹנָה וּשְׁלֹשִׁים יוֹם שֶׁהֵם חֲמִשָׁה שָׁבוּעוֹת וּשְׁלֹשָׁה יָמִים לָעֽוֹמֶר",
        39: "הַיוֹם תִּשְׁעָה וּשְׁלֹשִׁים יוֹם שֶׁהֵם חֲמִשָׁה שָׁבוּעוֹת וְאַרְבָּעָה יָמִים לָעֽוֹמֶר",
        40: "הַיוֹם אַרְבָּעִים יוֹם שֶׁהֵם חֲמִשָׁה שָׁבוּעוֹת וַחֲמִשָׁה יָמִים לָעֽוֹמֶר",
        41: "הַיוֹם אֶחָד וְאַרְבָּעִים יוֹם שֶׁהֵם חֲמִשָׁה שָׁבוּעוֹת וְשִׁשָׁה יָמִים לָעֽוֹמֶר",
        42: "הַיוֹם שְׁנַֽיִם וְאַרְבָּעִים יוֹם שֶׁהֵם שִׁשָׁה שָׁבוּעוֹת לָעֽוֹמֶר",
        43: "הַיוֹם שְׁלֹשָׁה וְאַרְבָּעִים יוֹם שֶׁהֵם שִׁשָׁה שָׁבוּעוֹת וְיוֹם אֶחָד לָעֽוֹמֶר",
        44: "הַיוֹם אַרְבָּעָה וְאַרְבָּעִים יוֹם שֶׁהֵם שִׁשָׁה שָׁבוּעוֹת וּשְׁנֵי יָמִים לָעֽוֹמֶר",
        45: "הַיוֹם חֲמִשָׁה וְאַרְבָּעִים יוֹם שֶׁהֵם שִׁשָׁה שָׁבוּעוֹת וּשְׁלֹשָׁה יָמִים לָעֽוֹמֶר",
        46: "הַיוֹם שִׁשָׁה וְאַרְבָּעִים יוֹם שֶׁהֵם שִׁשָׁה שָׁבוּעוֹת וְאַרְבָּעָה יָמִים לָעֽוֹמֶר",
        47: "הַיוֹם שִׁבְעָה וְאַרְבָּעִים יוֹם שֶׁהֵם שִׁשָׁה שָׁבוּעוֹת וַחֲמִשָׁה יָמִים לָעֽוֹמֶר",
        48: "הַיוֹם שְׁמוֹנָה וְאַרְבָּעִים יוֹם שֶׁהֵם שִׁשָׁה שָׁבוּעוֹת וְשִׁשָׁה יָמִים לָעֽוֹמֶר",
        49: "הַיוֹם תִּשְׁעָה וְאַרְבָּעִים יוֹם שֶׁהֵם שִׁבְעָה שָׁבוּעוֹת לָעֽוֹמֶר"
    }
]

# <img src="https://raw.githubusercontent.com/rt400/Hebcal-Jewish-Calendar/main/custom_components/hebcal_ui/brand/icon%402x.png" width="65" height="65" align="center"> Hebcal Jewish Calendar for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/rt400/Hebcal-Jewish-Calendar.svg)](https://github.com/rt400/Hebcal-Jewish-Calendar/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

A modern, highly accurate, and fully-featured Home Assistant integration for the Jewish calendar, Halachic times (Zmanim), Sabbaths, and Holidays. Powered by the [Hebcal API](https://www.hebcal.com/) with a robust local fallback engine.

This integration provides a comprehensive suite of sensors designed specifically for smart home automations based on Jewish laws and schedules. Whether you need to disable motion sensors during Shabbat, automate lights for Yom Tov, or get notified about candle lighting times, this integration handles all the complex calculations for you.

---

## 🌟 Key Features

*   🛑 **Smart "Issur Melacha" (Work Prohibition) Engine:** A highly advanced boolean sensor that accurately calculates when work is forbidden. It seamlessly handles complex overlapping scenarios, such as when Shabbat immediately follows Yom Tov or vice versa.
*   🕯️ **Candle Lighting & Havdalah Times:** Precise local times for entering and exiting Sabbaths and holidays. Includes offline mathematical fallbacks to ensure your automations run even during internet outages.
*   📅 **Hebrew Date & Parashat Hashavua:** Tracks the current Hebrew calendar date, Jewish month, and the weekly Torah reading.
*   ☀️ **Daily Halachic Times (Zmanim):** Automatically calculates localized Zmanim (e.g., Alot Hashachar, Netz, Shkia, Tzeit Hakochavim) based on your exact coordinates and timezone.
*   🌾 **Sefirat HaOmer:** Daily tracking of the Omer count during the relevant season.
*   🌍 **Diaspora & Israel Modes:** Fully supports the differing holiday schedules between Israel and the Diaspora.

---

## ⚙️ Configuration & Settings

Configuration is done entirely via the Home Assistant UI (Config Flow). You can customize the integration to match your exact local customs and Halachic requirements:

*   **Location (Latitude, Longitude, Timezone):** The core parameters used to calculate accurate local sunset and astronomical times (Zmanim).
*   **Diaspora Mode (חו"ל):** Enable this if you live outside of Israel. It ensures holidays are correctly observed for two days (Yom Tov Sheni) and adjusts the weekly Torah portion (Parashat Hashavua) readings, which sometimes differ between Israel and the Diaspora.
*   **Candle Lighting Offset:** Defines how many minutes before sunset candle lighting is scheduled. You can toggle **Jerusalem Mode** (40 minutes before sunset) or keep the standard setting (18 minutes before sunset).
*   **Havdalah Offset:** Defines how many minutes after sunset Shabbat and holidays end. You can set this to your community's custom (e.g., 42, 50, or 72 minutes for Rabbeinu Tam).
*   **Use Tzeit Hakochavim:** When enabled, the integration will calculate Havdalah based on the astronomical *Tzeit Hakochavim* (appearance of three stars) for your specific coordinates, rather than relying on a fixed minute offset.
*   **Time Format:** Choose whether the sensors display times in a 12-hour (AM/PM) or 24-hour format.
*   **Language:** Set the language for the sensor values, event titles, and holiday names (English or Hebrew).

---

## 📥 Installation

### Option 1: HACS (Recommended)
This integration is highly recommended to be installed via [HACS](https://hacs.xyz/) for easy updates.

1. Open HACS in your Home Assistant instance.
2. Click the three-dot menu in the top right corner and select **Custom repositories**.
3. Add the URL of this repository (`https://github.com/rt400/Hebcal-Jewish-Calendar`) and select `Integration` as the category.
4. Click **Add**, search for "Hebcal Jewish Calendar" in HACS, and click download.
5. Restart Home Assistant.
6. Go to **Settings** > **Devices & Services** > **Add Integration** and search for "Hebcal Jewish Calendar".

### Option 2: Manual Installation
1. Download the `hebcal` folder from the latest release on the [Releases page](../../releases).
2. Copy the `hebcal` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.
4. Go to **Settings** > **Devices & Services** > **Add Integration** and search for "Hebcal Jewish Calendar".

---

## 🐛 Reporting Issues & Feedback

Halachic calculations and calendar edge cases can be incredibly complex, and occasional errors or unexpected behaviors might occur. 

If you notice any inaccuracies in the times, missing events, or if you simply have a suggestion for improvement, I would be more than happy to hear from you! Please feel free to [open an Issue](https://github.com/rt400/Hebcal-Jewish-Calendar/issues) to help make this integration better and more accurate for everyone.

---

## 👨‍‍💻 Author
Developed and maintained by **Yuval Mejahez** (@rt400).

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

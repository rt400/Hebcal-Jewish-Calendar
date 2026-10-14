# <img src="https://raw.githubusercontent.com/rt400/Hebcal-Jewish-Calendar/main/custom_components/hebcal_ui/brand/icon%402x.png" width="65" height="65" align="center"> Hebcal Jewish Calendar for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/rt400/Hebcal-Jewish-Calendar.svg)](https://github.com/rt400/Hebcal-Jewish-Calendar/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

A modern, highly accurate, and fully-featured Home Assistant integration for the Jewish calendar, Halachic times (Zmanim), Sabbaths, and Holidays. Powered by a hybrid engine combining the [Hebcal API](https://www.hebcal.com/) with a robust local fallback database.

This integration provides a comprehensive suite of sensors designed specifically for smart home automations based on Jewish laws and schedules. Whether you need to disable motion sensors during Shabbat, automate ACs before Yom Tov, or get notified about candle lighting times, this integration handles all the complex calculations for you.

---

## 🌟 Key Features

*   🌐 **Hybrid Data Engine (New!):** Seamlessly connects to the online Hebcal server for real-time accuracy, while maintaining a fully functional automatic local fallback database. During internet outages, it switches to offline mode automatically so your automations never break. You can also run it in strict "Offline Only" mode.
*   🛑 **Smart "Issur Melacha" (Work Prohibition) Engine:** A highly advanced boolean sensor that accurately calculates when work is forbidden, handling complex overlapping scenarios like Shabbat immediately following Yom Tov.
*   ⏱️ **Smart Automations Buffers (New!):** Define custom "buffer" minutes before Shabbat enters and after it exits to trigger automations (like turning on the AC 30 minutes before candle lighting).
*   🌍 **Bilingual & Dynamic UI (New!):** Full dynamic support for both English (transliterated) and Hebrew directly from the modern Home Assistant UI setup, including sliders and dropdowns.
*   🕯️ **Candle Lighting & Havdalah Times:** Precise local times for entering and exiting Sabbaths and holidays based on exact coordinates and community customs (e.g., Jerusalem 40 minutes, Rabbeinu Tam 72 minutes).
*   ☀️ **Daily Halachic Times (Zmanim):** Automatically calculates localized Zmanim (e.g., Alot Hashachar, Netz, Shkia, Tzeit Hakochavim) based on your coordinates and timezone.

---

## ⚙️ Configuration & Settings

Configuration is done entirely via the modern Home Assistant UI (Config Flow) using intuitive sliders and dropdown selectors `(Settings -> Devices & Services -> Hebcal -> Configure)`:

*   **Data Connection Mode:** 
    *   *Online (Recommended):* Syncs with the server with an automatic local fallback.
    *   *Offline Only:* Fully independent calculation from the local database without internet reliance.
*   **Language:** Choose English (transliterated) or Hebrew ("עברית"). This affects event names, Torah portions, Hebrew dates, and the daily Omer count text.
*   **Location (Latitude, Longitude, Timezone):** The core parameters used to calculate accurate local sunset and astronomical times (Zmanim).
*   **Havdalah Minutes:** Defines the number of minutes after sunset to calculate the end of Shabbat or holidays (e.g., 42 for Geonim, 50 for Jerusalem, 72 for Rabbeinu Tam). Set precisely using the UI slider.
*   **Minutes Before Shabbat/Holiday Entrance:** A time buffer to activate sensors *before* the actual calculated start time (useful for "pre-Shabbat" automations).
*   **Minutes After Shabbat/Holiday End:** A time buffer to keep sensors active *after* the official end time.
*   **Jerusalem Candle Lighting:** Enable to use the strict Jerusalem custom of lighting candles 40 minutes before sunset (instead of the standard 18).
*   **Use Tzeit Hakochavim:** Calculates Havdalah based on the astronomical *Tzeit Hakochavim* (appearance of stars) for your specific coordinates, rather than a fixed minute offset.
*   **Diaspora Mode (חו"ל):** Crucial for users outside of Israel. Ensures holidays are correctly observed for two days (Yom Tov Sheni) and adjusts the weekly Torah portion readings accordingly.
*   **12-Hour Time Format:** Display times in 12-hour (AM/PM) or 24-hour format.
*   **Omer Count Style:** Choose between the Traditional Yemenite custom or the Ashkenazi/Sephardic custom for the Sefirat HaOmer text.

---

## 📊 Available Entities

The integration exposes a variety of sensors to power your automations:

### Binary Sensors
*   `binary_sensor.is_shabbat` - Active when Shabbat is observed (respects the entrance/exit buffer minutes).
*   `binary_sensor.is_yom_tov` - Active when a Holiday is observed.
*   `binary_sensor.issur_melacha` - Active during any period where work is prohibited (Shabbat and Yom Tov combined).

### Data Sensors
*   `sensor.hebrew_date` - The current Hebrew date.
*   `sensor.torah_portion` - This week's Parashat Hashavua.
*   `sensor.holiday_name` - The name of the current or upcoming holiday.
*   `sensor.omer_count` - The full daily text for Sefirat HaOmer.
*   `sensor.shabbat_entry` / `sensor.shabbat_exit` - Exact dates and times for the upcoming Shabbat.
*   `sensor.halachic_times` - A sensor containing attributes for all daily Zmanim (Dawn, Sunrise, Latest Shema, Midday, Sunset, Nightfall, etc.).
*   `sensor.data_source` - Displays the currently active engine (`Online Server` or `Local Database`).

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

## 👨‍💻 Author
Developed and maintained by **Yuval Mejahez** (@rt400).

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

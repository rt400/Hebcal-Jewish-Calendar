# Hebcal Jewish Calendar for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/release/rt400/YOUR-NEW-REPO-NAME.svg)](https://github.com/rt400/Hebcal-Jewish-Calendar/releases)

A modern, fully-featured Home Assistant integration for the Jewish calendar, Halachic times (Zmanim), Sabbaths, and Holidays. Powered by [Hebcal](https://www.hebcal.com/).

This integration provides a comprehensive set of sensors to help you automate your smart home based on Jewish laws and times (e.g., turning off lights automatically before Shabbat or restricting automated vacuums during Yom Tov).

## 🌟 Features

Provides real-time sensors based on your local coordinates:

* **Work Prohibition (Issur Melacha):** Boolean sensor indicating if work is currently forbidden.
* **Shabbat & Yom Tov Status:** Dedicated boolean sensors (`Is Shabbat`, `Is Yom Tov`).
* **Candle Lighting & Havdalah Times:** Exact start and end times for Sabbaths and Holidays.
* **Halachic Times (Zmanim):** Daily halachic times configured for your location.
* **Hebrew Date:** The current Hebrew calendar date.
* **Torah Portion (Parashat Hashavua):** The weekly Torah reading.
* **Omer Count:** Daily tracking of Sefirat HaOmer.
* **Upcoming Events:** Information on upcoming major holidays or fasts.

## 📥 Installation

### Option 1: HACS (Recommended)
This integration is HACS compatible. To install:
1. Open HACS in your Home Assistant instance.
2. Click on the 3-dots menu in the top right corner and select **Custom repositories**.
3. Add the URL of this repository and select `Integration` as the category.
4. Click **Add**, then search for "Hebcal Jewish Calendar" and install it.
5. Restart Home Assistant.

### Option 2: Manual Installation
1. Download the latest release from the [Releases page](../../releases).
2. Extract and copy the `custom_components/hebcal` directory into your Home Assistant `custom_components` folder.
3. Restart Home Assistant.

## ⚙️ Configuration

Configuration is done entirely via the Home Assistant UI (Config Flow). No `configuration.yaml` editing is required!

1. Go to **Settings** -> **Devices & Services**.
2. Click **+ Add Integration**.
3. Search for **Hebcal Jewish Calendar**.
4. Follow the on-screen instructions to set up your location and preferences.

## 👨‍💻 Author
Developed by **Yuval Mejahez** (@rt400).

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

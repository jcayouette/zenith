from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from zenith.sky.clock import system_timezone

BackendName = Literal["simulator", "picamera2", "indi", "mqtt_libcamera"]
Binning = Literal[1, 2]

_HQ_TUNING = "/usr/share/libcamera/ipa/rpi/pisp/imx477.json"


def _f(description: str, **kwargs):
    return Field(description=description, **kwargs)


def detect_camera_backend() -> BackendName:
    """Picamera2 on a Pi with python3-picamera2; simulator everywhere else."""
    try:
        import picamera2  # noqa: F401
    except ImportError:
        return "simulator"
    return "picamera2"


def default_tuning_file() -> str:
    return _HQ_TUNING if Path(_HQ_TUNING).is_file() else ""


def default_timezone() -> str:
    return system_timezone()


class LocationSettings(BaseModel):
    latitude: float = _f(
        "Site latitude in decimal degrees (positive north). Used for day/night, moon mode, "
        "satellite passes, aircraft, and the Sky map. Saving a street address overwrites this "
        "with the geocoded house point.",
        default=0.0,
        ge=-90,
        le=90,
    )
    longitude: float = _f(
        "Site longitude in decimal degrees (positive east).",
        default=0.0,
        ge=-180,
        le=180,
    )
    elevation_m: float = _f(
        "Site elevation above sea level in metres. Small effect on refraction and horizon.",
        default=0.0,
        ge=-400,
        le=9000,
    )
    timezone_auto: bool = Field(
        default=True,
        title="Automatic DST",
        description=(
            "Follow the Pi timezone from timedatectl, including CET/CEST. "
            "Day and night still switch on sun altitude at this site, not on a clock hour. "
            "NTP keeps that clock accurate so sunset is computed correctly."
        ),
    )
    timezone: str = _f(
        "IANA timezone for folder dates and overlays (Europe/Berlin, America/Denver, …). "
        "Ignored while Automatic DST is on — Zenith then uses the Pi timezone. "
        "Named zones already include daylight saving; do not use a fixed UTC offset.",
        default_factory=default_timezone,
    )
    keogram_angle_deg: float = _f(
        "Rotate frames so the meridian is vertical before extracting the keogram column. "
        "Adjust until Polaris (or the celestial pole) sits on a vertical line.",
        default=0.0,
        ge=-180,
        le=180,
    )
    night_sun_altitude_deg: float = _f(
        "Sun altitude that starts astronomical night. −18° is astronomical twilight; "
        "−12° nautical; −6° civil. Lower means a longer 'night' capture profile.",
        default=-18.0,
        ge=-24,
        le=0,
    )
    name: str = _f(
        "Short label for the Sky map pin (e.g. Allsky, garden, roof).",
        default="",
        title="Site name",
    )
    address: str = _f(
        "Street and house number. Shown on the Sky map pin with your city.",
        default="",
        title="Street address",
    )
    postcode: str = _f(
        "Postal code for this site (e.g. 91052).",
        default="",
        title="Postcode",
    )
    city: str = _f(
        "Town or city (e.g. Erlangen). Shown under the zenith when the Site layer is on.",
        default="",
        title="City",
    )

    def resolved_timezone(self) -> str:
        if self.timezone_auto:
            return system_timezone() or self.timezone
        return self.timezone


class CameraCommonSettings(BaseModel):
    backend: BackendName = _f(
        "How Zenith talks to the sensor. simulator = synthetic sky for development. "
        "picamera2 = local Raspberry Pi CSI (HQ / IMX477 on acmeastro). "
        "indi = USB astro cameras via indiserver (ZWO, QHY, Svbony, …). "
        "mqtt_libcamera = a remote Pi that owns its own camera. Defaults to picamera2 when "
        "the Picamera2 package is importable (this Pi), otherwise simulator.",
        default_factory=detect_camera_backend,
    )
    device: str = _f(
        "Camera index or INDI CCD name. For Picamera2 this is usually 0. "
        "For INDI, pick the CCD reported by indiserver (e.g. ZWO CCD ASI533MC).",
        default="0",
    )
    capture_day: bool = _f("Take frames during daytime.", default=True)
    save_day: bool = _f(
        "Archive daytime frames (DNG/PNG, not JPEG). Night frames are always saved when "
        "capture is running. Turn off to save disk if you only care about the night sky.",
        default=False,
    )
    capture_night: bool = _f("Take frames after the sun drops below the night threshold.", default=True)
    binning: Binning = _f(
        "1 = full resolution (HQ is 4056×3040). 2 = 2×2 binning for better night SNR and "
        "less CPU/disk. Binning is recommended on the Pi for overnight runs.",
        default=2,
    )
    jpeg_quality: int = _f(
        "JPEG quality 1–100 for live preview and archive thumbs only. Science frames are "
        "DNG (Picamera2) or lossless PNG — never JPEG.",
        default=90,
        ge=40,
        le=100,
    )
    flip_h: bool = _f("Mirror the image horizontally so east/west match the sky.", default=False)
    flip_v: bool = _f("Mirror the image vertically. Use with rotation to put north up.", default=False)
    rotation_deg: Literal[0, 90, 180, 270] = _f(
        "Rotate the saved image in 90° steps after capture.",
        default=0,
    )
    extra_delay_s: float = _f(
        "Pause after each science frame before the next. Ignored in focus mode. "
        "0 means 'as fast as the shutter + DNG write allow'.",
        default=0.0,
        ge=0,
        le=300,
    )
    focus_mode: bool = _f(
        "Focus / live preview. On: JPEG only (no DNG/PNG, no extra delay, no overlay) so you "
        "can rack the lens and tweak colour. Shutter uses the same IMX477 range as science "
        "mode (100 µs–120 s). Off: archive 12-bit DNG + lossless PNG.",
        default=False,
        title="Focus mode",
    )
    save_raw: bool = _f(
        "Write the sensor file: 12-bit DNG on Picamera2 (HQ / IMX477), lossless PNG on the "
        "simulator. This is the science archive — keep it on. HQ DNG is large; NVMe is fine.",
        default=True,
    )
    save_png: bool = _f(
        "Also write a lossless PNG of the linear RGB (no overlay, no JPEG compression) for "
        "timelapses and tools that cannot open DNG. Disable if disk is tight; DNG remains.",
        default=True,
    )
    save_jpeg: bool = _f(
        "Also write a full-resolution JPEG. Off by default — JPEG throws away faint stars "
        "and colour. Live view and thumbs already use JPEG.",
        default=False,
    )


class Picamera2Settings(BaseModel):
    tuning_file: str = _f(
        "libcamera IPA tuning JSON. On Raspberry Pi 5 with the HQ camera this is typically "
        "/usr/share/libcamera/ipa/rpi/pisp/imx477.json. Leave empty to use the default.",
        default_factory=default_tuning_file,
    )
    awb_enable_day: bool = _f(
        "Let libcamera auto white-balance during the day. Applies in focus and archive. "
        "Off (default) keeps camera colour as-is so the Red/Green/Blue sliders match both modes.",
        default=False,
    )
    colour_gain_r: float = _f(
        "Red gain as a float. 1.0 is camera data unchanged, 0.0 removes red. Applied to the "
        "live JPEG; also sent to the HQ ISP (with blue) when AWB is off. DNG is never multiplied.",
        default=1.0,
        ge=0.0,
        le=32.0,
        title="Red gain",
    )
    colour_gain_g: float = _f(
        "Green gain as a float. 1.0 is camera data unchanged, 0.0 removes green. Software on "
        "the live JPEG only — the IMX477 ISP has no separate green ColourGain.",
        default=1.0,
        ge=0.0,
        le=32.0,
        title="Green gain",
    )
    colour_gain_b: float = _f(
        "Blue gain as a float. 1.0 is camera data unchanged, 0.0 removes blue. Live JPEG always; "
        "ISP when AWB is off. Lower this if the preview looks too blue.",
        default=1.0,
        ge=0.0,
        le=32.0,
        title="Blue gain",
    )
    sharpness: float = _f(
        "ISP sharpening. Too high creates rings around stars. 0–1 is usually enough.",
        default=0.5,
        ge=0,
        le=16,
    )
    contrast: float = _f("ISP contrast. 1.0 is neutral (camera data as-is).", default=1.0, ge=0, le=2)
    saturation: float = _f("ISP saturation. 1.0 is neutral.", default=1.0, ge=0, le=2)
    denoise: Literal["off", "cdn_off", "cdn_fast", "cdn_hq"] = _f(
        "Pi ISP denoise. cdn_hq smears faint stars — prefer off or cdn_off for astronomy.",
        default="cdn_off",
    )


class IndiSettings(BaseModel):
    host: str = _f("indiserver hostname. localhost if INDI runs on the same Pi.", default="localhost")
    port: int = _f("indiserver port (default 7624).", default=7624, ge=1, le=65535)
    timeout_s: float = _f("Seconds to wait for a CCD blob after starting an exposure.", default=60, ge=1, le=600)
    cooler_enable: bool = _f("Enable CCD cooler if the camera has one (ZWO, QHY, …).", default=False)
    cooler_target_c: float = _f("Cooler set-point in °C. Ignored when cooler is off.", default=-10.0, ge=-40, le=30)
    usb_bandwidth: int = _f(
        "ZWO-style USB bandwidth 40–100. Lower if you see dropped frames on a hub.",
        default=80,
        ge=40,
        le=100,
    )


class MqttCameraSettings(BaseModel):
    broker: str = _f("MQTT broker for a remote Pi camera agent.", default="localhost")
    port: int = _f("MQTT port.", default=1883, ge=1, le=65535)
    expose_topic: str = _f("Topic used to request an exposure on the remote Pi.", default="zenith/camera/expose")
    result_topic: str = _f("Topic the remote Pi publishes JPEG + metadata on.", default="zenith/camera/frame")
    remote_id: str = _f("Id of the remote camera agent, if several Pis publish to one broker.", default="remote-0")


class ExposureProfile(BaseModel):
    auto_exposure: bool = _f(
        "Zenith mean-target auto-exposure (not libcamera AE). Measures image brightness and "
        "servos shutter, then gain, toward the target ADU. Use this at night.",
        default=True,
    )
    exposure_us: int = _f(
        "Manual exposure in microseconds when auto-exposure is off. 1_000_000 = 1 second. "
        "HQ IMX477 range is 100 µs–120 s. Night: start around 8–15 s.",
        default=1_000_000,
        ge=100,
        le=120_000_000,
    )
    max_exposure_us: int = _f(
        "Longest shutter auto-exposure is allowed to use. Night: try 15_000_000 (15 s) first. "
        "HQ IMX477 max in Zenith is 120 s.",
        default=15_000_000,
        ge=1000,
        le=120_000_000,
    )
    gain: float = _f("Manual analogue gain when auto-exposure is off. HQ unity is ~1, max ~22.", default=1.0, ge=1, le=22)
    max_gain: float = _f(
        "Highest analogue gain auto-exposure may use. High gain = more noise and hot pixels. "
        "Prefer longer exposure over maxing gain. IMX477 analogue max is about 22.",
        default=8.0,
        ge=1,
        le=22,
    )
    target_mean: float = _f(
        "Target mean pixel value 0–1 for auto-exposure (camera RGB, no display stretch). "
        "0.18 is a dark but readable night sky. 0.35–0.45 suits daytime.",
        default=0.20,
        ge=0.02,
        le=0.8,
    )


class ProductSettings(BaseModel):
    keogram_enabled: bool = _f(
        "Build a keogram by appending a meridian column from every saved night frame. "
        "keogram_realtime.jpg updates live; keogram.jpg is frozen at sunrise.",
        default=True,
    )
    keogram_slice_px: int = _f(
        "Pixels averaged around the meridian when sampling a keogram column. "
        "3–7 reduces noise; 1 is a true single-pixel slice.",
        default=5,
        ge=1,
        le=31,
    )
    startrails_enabled: bool = _f(
        "Maximum-stack startrails from night frames that pass the ADU window and minimum star count.",
        default=True,
    )
    startrails_min_stars: int = _f(
        "Skip a frame for startrails if fewer than this many stellar peaks are found. "
        "Cloudy or fogged nights stay out of the stack.",
        default=12,
        ge=0,
        le=5000,
    )
    startrails_adu_min: float = _f(
        "Minimum mean ADU (0–1) for a frame to enter the startrail stack. "
        "Rejects closed-shutter or extremely dark failures.",
        default=0.03,
        ge=0.0,
        le=0.8,
    )
    startrails_adu_max: float = _f(
        "Maximum mean ADU (0–1) for a frame to enter the startrail stack. "
        "Rejects washed-out moon or twilight frames that would smear the trails.",
        default=0.42,
        ge=0.05,
        le=1.0,
    )
    timelapse_enabled: bool = _f(
        "Encode an H.264 timelapse at sunrise (and on demand from Archive). "
        "Prefers 12-bit DNG developed with a fixed stretch; falls back to PNG if there is no raw.",
        default=True,
    )
    timelapse_fps: int = _f(
        "Playback frames per second for the full-night timelapse.",
        default=24,
        ge=1,
        le=60,
    )
    timelapse_from_raw: bool = _f(
        "Develop 12-bit DNG (Bayer demosaic, camera white balance, then your R/G/B sliders) "
        "and encode that as the timelapse. Off: use the ISP PNG sequence instead.",
        default=True,
        title="Timelapse from RAW",
    )
    timelapse_bright: float = _f(
        "Fixed develop brightness for DNG timelapses. Same value for every frame so the video "
        "does not flicker. 1 is as-shot; 2–4 is typical for night all-sky.",
        default=2.5,
        ge=0.5,
        le=16.0,
        title="RAW develop brightness",
    )
    mini_timelapse_enabled: bool = _f(
        "Also encode a smaller preview timelapse for the archive page.",
        default=True,
    )
    mini_timelapse_width: int = _f(
        "Pixel width of the mini timelapse. Height follows the frame aspect ratio.",
        default=640,
        ge=160,
        le=1920,
    )
    mini_timelapse_fps: int = _f(
        "Playback frames per second for the mini timelapse (often a bit faster than the full file).",
        default=30,
        ge=1,
        le=60,
    )
    thumb_width: int = _f(
        "Long-edge size in pixels for archive thumbnails (JPEG, preview only).",
        default=320,
        ge=80,
        le=1280,
    )
    detections_enabled: bool = _f(
        "Find streaks on night frames (meteors, aircraft, satellites) and list them on Detections. "
        "Uses frame-to-frame difference; cloudy frames are skipped.",
        default=True,
        title="Streak detections",
    )
    detections_min_length_px: int = _f(
        "Minimum streak length in pixels on the 320-wide detection image. "
        "Raise this if insects and noise show up; lower it to catch faint meteors.",
        default=14,
        ge=4,
        le=120,
        title="Min streak length",
    )
    detections_min_aspect: float = _f(
        "How elongated a blob must be (length / width). Stars and hot pixels are round; meteors are not.",
        default=3.2,
        ge=1.5,
        le=20.0,
        title="Min streak aspect",
    )


class OverlaySettings(BaseModel):
    enabled: bool = _f(
        "Burn text and cardinals into the live preview and thumbs. Raw DNG/PNG archives "
        "are never overlaid.",
        default=True,
    )
    show_exposure: bool = _f("Show shutter time on the overlay.", default=True)
    show_gain: bool = _f("Show analogue gain on the overlay.", default=True)
    show_sun_moon: bool = _f("Show sun and moon altitude.", default=True)
    cardinals: bool = _f("Draw N/E/S/W around the horizon ring. Requires keogram/compass angle to be correct.", default=True)


class SkySettings(BaseModel):
    constellations: bool = _f("Draw constellation stick figures on the Sky page.", default=True)
    constellation_names: bool = _f("Label constellations on the Sky page.", default=True)
    asterisms: bool = _f(
        "Draw common visual-astronomy asterisms (Big Dipper, Summer Triangle, Teapot, …).",
        default=True,
    )
    star_names: bool = _f("Label the brightest named stars on the Sky page.", default=True)
    grid: bool = _f("Draw altitude circles and azimuth spokes on the Sky page.", default=False)
    planets: bool = _f("Mark the sun and moon when they are above the horizon.", default=True)
    satellites: bool = _f(
        "Track Celestrak satellites on the Sky page (stations, visual, Starlink, GNSS, …).",
        default=True,
    )
    aircraft: bool = _f(
        "Radar-style ADS-B overlay on the local 80 km ground map. Inbound flights that "
        "will pass within 50 km show as green radar blips on the rim. "
        "Uses OpenSky when credits remain, otherwise a community ADS-B feed.",
        default=True,
        title="Aircraft",
    )
    map: bool = _f(
        "Sharp OpenStreetMap of the local 80 km around the site. Same north and overlay-radius as the sky disk.",
        default=False,
        title="Map",
    )
    site_label: bool = _f(
        "Show the observatory name and town under the zenith on the Sky overlay.",
        default=True,
        title="Site label",
    )
    map_brightness: float = _f(
        "How strong the ground map is drawn over the live frame. 0 is off, 1 is full tiles.",
        default=0.62,
        ge=0.1,
        le=1.0,
        title="Map brightness",
    )
    map_style: Literal["street", "satellite", "hybrid", "terrain", "elevation"] = _f(
        "Basemap under the Sky overlay. Streets and hybrid keep place names; satellite and "
        "terrain are imagery; elevation is OpenTopoMap contours.",
        default="street",
        title="Map style",
    )
    mag_limit: float = _f(
        "Faintest catalog stars drawn on the Sky overlay (and painted by the simulator). "
        "Constellation and asterism lines only connect stars at or brighter than this. "
        "0 hides all catalog stars.",
        default=5.0,
        ge=0.0,
        le=6.0,
    )
    star_name_mag: float = _f(
        "Name catalog stars brighter than this magnitude on the Sky page. 0 hides all names.",
        default=1.85,
        ge=0.0,
        le=6.0,
    )
    min_sat_alt_deg: float = _f(
        "Ignore satellites below this altitude (degrees) for the overlay and pass list. "
        "0 shows everything above the horizon, like Stellarium.",
        default=0.0,
        ge=0.0,
        le=70.0,
    )
    sat_icon_scale: float = _f(
        "Satellite icon size on the Sky overlay. 1 is the default tiny marker.",
        default=1.0,
        ge=0.4,
        le=4.0,
        title="Satellite icon size",
    )
    simulator_catalog: bool = _f(
        "Simulator paints a catalog sky at this site and time, even during the day, so overlays "
        "can be developed without a real night. Off: daytime simulator stays blue.",
        default=True,
        title="Simulator catalog sky",
    )
    horizon: float = _f(
        "How far the horizon ring sits in the frame. 1.0 puts the horizon on the long edge "
        "so the overlay fills a 4:3 HQ image. Lower if your lens circle is smaller.",
        default=1.0,
        ge=0.4,
        le=1.5,
        title="Horizon fill",
    )
    constellation_line_px: float = _f(
        "Constellation stick-figure thickness in pixels on the Sky page.",
        default=1.0,
        ge=0.5,
        le=6.0,
        title="Line thickness",
    )


class DewSettings(BaseModel):
    mode: Literal["off", "on", "auto"] = _f(
        "USB dew pad: off, forced on, or auto from Open-Meteo RH / dew point at the site. "
        "Auto only heats at night when the air is wet enough — not 24/7.",
        default="off",
        title="Dew heater",
    )
    interval_min: int = _f(
        "How often auto re-checks humidity (minutes). 3–10 is for testing; 10–15 is overnight.",
        default=10,
        ge=1,
        le=60,
        title="Check interval",
    )
    rh_on: float = _f(
        "Turn the pad on at night when relative humidity is at least this percent.",
        default=80,
        ge=50,
        le=100,
        title="RH on threshold",
    )
    spread_c: float = _f(
        "Turn the pad on at night when air temp minus dew point is this many °C or less. "
        "The dome runs colder than the forecast, so 4 °C is a typical summer trip.",
        default=4.0,
        ge=0.5,
        le=12.0,
        title="Dew-spread on",
    )


class ZenithSettings(BaseModel):
    location: LocationSettings = Field(default_factory=LocationSettings)
    camera: CameraCommonSettings = Field(default_factory=CameraCommonSettings)
    picamera2: Picamera2Settings = Field(default_factory=Picamera2Settings)
    indi: IndiSettings = Field(default_factory=IndiSettings)
    mqtt_camera: MqttCameraSettings = Field(default_factory=MqttCameraSettings)
    day: ExposureProfile = Field(
        default_factory=lambda: ExposureProfile(
            auto_exposure=True,
            exposure_us=800,
            max_exposure_us=80_000,
            gain=1.0,
            max_gain=2.0,
            target_mean=0.40,
        )
    )
    night: ExposureProfile = Field(
        default_factory=lambda: ExposureProfile(
            auto_exposure=True,
            exposure_us=8_000_000,
            max_exposure_us=15_000_000,
            gain=4.0,
            max_gain=12.0,
            target_mean=0.18,
        )
    )
    overlay: OverlaySettings = Field(default_factory=OverlaySettings)
    sky: SkySettings = Field(default_factory=SkySettings)
    products: ProductSettings = Field(default_factory=ProductSettings)
    dew: DewSettings = Field(default_factory=DewSettings)

    model_config = {"title": "Zenith settings", "extra": "ignore"}

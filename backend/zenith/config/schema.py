from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

BackendName = Literal["simulator", "picamera2", "indi", "mqtt_libcamera"]
Binning = Literal[1, 2]


def _f(description: str, **kwargs):
    return Field(description=description, **kwargs)


class LocationSettings(BaseModel):
    latitude: float = _f(
        "Site latitude in decimal degrees (positive north). Used for day/night, moon mode, "
        "satellite passes, and aurora probability.",
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
    timezone: str = _f(
        "IANA timezone for night dating and overlays, e.g. America/Denver or Europe/Amsterdam.",
        default="UTC",
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


class CameraCommonSettings(BaseModel):
    backend: BackendName = _f(
        "How Zenith talks to the sensor. simulator = synthetic sky for development. "
        "picamera2 = local Raspberry Pi CSI (HQ / IMX477 on acmeastro). "
        "indi = USB astro cameras via indiserver (ZWO, QHY, Svbony, …). "
        "mqtt_libcamera = a remote Pi that owns its own camera.",
        default="simulator",
    )
    device: str = _f(
        "Camera index or INDI CCD name. For Picamera2 this is usually 0. "
        "For INDI, pick the CCD reported by indiserver (e.g. ZWO CCD ASI533MC).",
        default="0",
    )
    capture_day: bool = _f("Take frames during daytime.", default=True)
    save_day: bool = _f(
        "Archive daytime JPEGs. Night frames are always saved when capture is running. "
        "Turn off to save disk if you only care about the night sky.",
        default=False,
    )
    capture_night: bool = _f("Take frames after the sun drops below the night threshold.", default=True)
    binning: Binning = _f(
        "1 = full resolution (HQ is 4056×3040). 2 = 2×2 binning for better night SNR and "
        "less CPU/disk. Binning is recommended on the Pi for overnight runs.",
        default=2,
    )
    jpeg_quality: int = _f(
        "JPEG quality 1–100. 90 is a good archive default. Lower for faster live previews.",
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
        "Pause after each exposure before starting the next. 0 means 'as fast as the shutter allows'.",
        default=0.0,
        ge=0,
        le=300,
    )
    save_raw: bool = _f(
        "Also write DNG (Picamera2) or FITS (INDI). Needed for proper darks and SQM. "
        "HQ full-res DNG is large — keep retention aggressive on SD cards; NVMe is fine.",
        default=False,
    )


class Picamera2Settings(BaseModel):
    tuning_file: str = _f(
        "libcamera IPA tuning JSON. On Raspberry Pi 5 with the HQ camera this is typically "
        "/usr/share/libcamera/ipa/rpi/pisp/imx477.json. Leave empty to use the default.",
        default="",
    )
    awb_enable_day: bool = _f(
        "Let libcamera auto white-balance during the day. Disable at night so colour of "
        "the sky and aurora stays consistent.",
        default=True,
    )
    colour_gain_r: float = _f(
        "Manual red gain when AWB is off. Typical HQ night starting point ~2.0.",
        default=2.0,
        ge=0.5,
        le=8,
    )
    colour_gain_b: float = _f(
        "Manual blue gain when AWB is off. Typical HQ night starting point ~1.8.",
        default=1.8,
        ge=0.5,
        le=8,
    )
    sharpness: float = _f(
        "ISP sharpening. Too high creates rings around stars. 0–1 is usually enough.",
        default=0.5,
        ge=0,
        le=16,
    )
    contrast: float = _f("ISP contrast. Leave near 1.0 and stretch in software instead.", default=1.0, ge=0, le=2)
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
        "HQ IMX477 on Pi 5 can do tens of seconds; start around 8–15 s at night.",
        default=1_000_000,
        ge=100,
        le=200_000_000,
    )
    max_exposure_us: int = _f(
        "Longest shutter auto-exposure is allowed to use. Night: try 15_000_000 (15 s) first.",
        default=15_000_000,
        ge=1000,
        le=200_000_000,
    )
    gain: float = _f("Manual analogue gain when auto-exposure is off. HQ unity is ~1.", default=1.0, ge=1, le=16)
    max_gain: float = _f(
        "Highest analogue gain auto-exposure may use. High gain = more noise and hot pixels. "
        "Prefer longer exposure over maxing gain.",
        default=8.0,
        ge=1,
        le=16,
    )
    target_mean: float = _f(
        "Target mean pixel value 0–1 after stretch. 0.18 is a dark but readable night sky. "
        "0.35–0.45 suits daytime.",
        default=0.20,
        ge=0.02,
        le=0.8,
    )


class OverlaySettings(BaseModel):
    enabled: bool = _f("Burn text and cardinals into saved JPEGs (live preview always has a clean option).", default=True)
    show_exposure: bool = _f("Show shutter time on the overlay.", default=True)
    show_gain: bool = _f("Show analogue gain on the overlay.", default=True)
    show_sun_moon: bool = _f("Show sun and moon altitude.", default=True)
    cardinals: bool = _f("Draw N/E/S/W around the horizon ring. Requires keogram/compass angle to be correct.", default=True)


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

    model_config = {"title": "Zenith settings"}

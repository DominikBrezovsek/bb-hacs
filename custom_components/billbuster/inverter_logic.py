from datetime import timedelta
import logging
import os

from deye_controller import SellProgrammer
import pandas as pd

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_INVERTER_IP,
    CONF_INVERTER_POWER,
    CONF_INVERTER_SERIAL,
    CONF_MAX_SOC,
    CONF_MIN_SOC,
    CONF_PEAK_CHARGE_POWER,
)

_LOGGER = logging.getLogger(__name__)


class BaseInverter:
    """Base class for inverter logic."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the inverter logic handler."""
        self.hass = hass
        self.entry = entry
        self.inverter_ip = self.entry.options.get(
            CONF_INVERTER_IP, self.entry.data.get(CONF_INVERTER_IP)
        )
        self.inverter_serial = self.entry.options.get(
            CONF_INVERTER_SERIAL, self.entry.data.get(CONF_INVERTER_SERIAL)
        )
        self.inverter_power = self.entry.options.get(
            CONF_INVERTER_POWER, self.entry.data.get(CONF_INVERTER_POWER)
        )
        self.peak_charge_power = self.entry.options.get(
            CONF_PEAK_CHARGE_POWER, self.entry.data.get(CONF_PEAK_CHARGE_POWER)
        )
        self.minSoC_percent = self.entry.options.get(
            CONF_MIN_SOC, self.entry.data.get(CONF_MIN_SOC)
        )
        self.maxSoC_percent = self.entry.options.get(
            CONF_MAX_SOC, self.entry.data.get(CONF_MAX_SOC)
        )

        self.df = None
        self._absolute_csv_path = "/share/opt_res_latest.csv"
        self.next_run = None

    def _resolve_csv_path(self) -> str | None:
        """Resolve potential relative path and check existence."""
        path = self._absolute_csv_path
        if not os.path.isabs(path):
            path = self.hass.config.path(path)

        if not os.path.exists(path):
            _LOGGER.error(
                "CSV file path does not exist during load: %s (resolved to %s)",
                self._absolute_csv_path,
                path,
            )
            return None
        self._absolute_csv_path = path
        return path

    def load_csv(self):
        """Load the CSV, convert timestamps, and sort data. Blocking I/O."""
        resolved_path = self._resolve_csv_path()
        if not resolved_path:
            self.df = pd.DataFrame()
            return False

        _LOGGER.info("Loading CSV from: %s", resolved_path)
        try:
            self.df = pd.read_csv(resolved_path, parse_dates=["timestamp"])
            if self.df.empty:
                _LOGGER.warning("Loaded CSV is empty: %s", resolved_path)
                return False
            self.df.sort_values("timestamp", inplace=True)
            _LOGGER.debug("CSV loaded successfully. Shape: %s", self.df.shape)
            return True
        except FileNotFoundError:
            _LOGGER.error(
                "The file at %s was not found (should have been checked already)",
                resolved_path,
            )
            self.df = pd.DataFrame()
        except pd.errors.EmptyDataError:
            _LOGGER.error("The CSV file is empty: %s", resolved_path)
            self.df = pd.DataFrame()
        except pd.errors.ParserError:
            _LOGGER.error("There was a problem parsing the CSV file: %s", resolved_path)
            self.df = pd.DataFrame()
        except Exception as e:
            _LOGGER.error(
                "An unexpected error occurred loading CSV %s: %s", resolved_path, e
            )
            self.df = pd.DataFrame()
        return False  # Indicate failure

    def generate_intervals(self):
        """Generate intervals. Should be implemented by subclasses."""
        raise NotImplementedError("Subclasses should implement this method")

    async def async_run_schedule_update(self):
        """Loads data, generates intervals, and updates inverter. Runs blocking code in executor. Returns True on success"""

        success = await self.hass.async_add_executor_job(self.load_csv)
        if not success or self.df is None or self.df.empty:
            _LOGGER.error(
                "Failed to load or process CSV data. Aborting schedule update"
            )
            return False

        intervals_df = await self.hass.async_add_executor_job(self.generate_intervals)

        if intervals_df is None or intervals_df.empty:
            _LOGGER.warning("No valid intervals generated from CSV data")
            return False

        _LOGGER.info(
            "Generated %d intervals. Attempting to program inverter", len(intervals_df)
        )
        try:
            await self.hass.async_add_executor_job(self._program_inverter, intervals_df)
            _LOGGER.info("Successfully programmed inverter schedule")
            self.next_run = intervals_df.tail(1)["stop_time"]
            return True
        except Exception as e:
            _LOGGER.error("Failed to program inverter schedule: %s", e)
            return False

    def _program_inverter(self, intervals_df: pd.DataFrame):
        """Blocking function to interact with SellProgrammer."""

        _LOGGER.debug(
            "Connecting to inverter %s (Serial: %s) for programming",
            self.inverter_ip,
            self.inverter_serial,
        )
        inverter_program = SellProgrammer(self.inverter_ip, int(self.inverter_serial))
        try:
            for index, interval in intervals_df.iterrows():
                mode = interval["mode"]
                start_time = interval["start_time"].strftime("%H:%M")
                stop_time_dt = interval["stop_time"]
                if interval["start_time"] == stop_time_dt:
                    stop_time_dt += timedelta(minutes=1)
                end_time = stop_time_dt.strftime("%H:%M")

                soc = int(
                    self.maxSoC_percent if mode == "charge" else self.minSoC_percent
                )
                power = int(
                    self.peak_charge_power if mode == "charge" else self.inverter_power
                )
                if mode == "idle":
                    power = 1

                _LOGGER.info(
                    f"Programming Interval {index + 1}: {start_time} - {end_time} ({mode}), Power: {power}, SoC: {soc}"
                )
                inverter_program.update_program(
                    index=int(index),
                    start_t=start_time,
                    stop_t=end_time,
                    soc=int(soc),
                    power=int(power),
                    grid_ch=str(mode == "charge"),
                    gen_ch=False,
                )

            inverter_program.show_as_screen()
            _LOGGER.debug("Uploading settings to inverter")
            inverter_program.upload_settings()
            _LOGGER.debug("Settings uploaded")
        except Exception as e:
            _LOGGER.error("Error during inverter programming sequence: %s", e)
            raise
        finally:
            try:
                _LOGGER.debug("Disconnecting from inverter")
                inverter_program.disconnect()
            except Exception as e:
                _LOGGER.warning("Error during SellProgrammer disconnect: %s", e)

    def update_from_config_entry(self, entry: ConfigEntry):
        """Update the inverter instance with new config entry data."""
        self.entry = entry
        self.inverter_ip = self.entry.options.get(
            CONF_INVERTER_IP, self.entry.data.get(CONF_INVERTER_IP)
        )
        self.inverter_serial = self.entry.options.get(
            CONF_INVERTER_SERIAL, self.entry.data.get(CONF_INVERTER_SERIAL)
        )
        self.inverter_power = self.entry.options.get(
            CONF_INVERTER_POWER, self.entry.data.get(CONF_INVERTER_POWER)
        )
        self.peak_charge_power = self.entry.options.get(
            CONF_PEAK_CHARGE_POWER, self.entry.data.get(CONF_PEAK_CHARGE_POWER)
        )
        self.minSoC_percent = self.entry.options.get(
            CONF_MIN_SOC, self.entry.data.get(CONF_MIN_SOC)
        )
        self.maxSoC_percent = self.entry.options.get(
            CONF_MAX_SOC, self.entry.data.get(CONF_MAX_SOC)
        )
        _LOGGER.debug("DeyeInverter updated with new config: %s", entry.options)

    async def async_run_schedule_update(self):
        """Loads data, generates intervals, and updates inverter. Runs blocking code in executor. Returns True on success."""

        success = await self.hass.async_add_executor_job(self.load_csv)
        if not success or self.df is None or self.df.empty:
            _LOGGER.error(
                "Failed to load or process CSV data. Aborting schedule update"
            )
            return False

        intervals_df = await self.hass.async_add_executor_job(self.generate_intervals)

        if intervals_df is None or intervals_df.empty:
            _LOGGER.warning("No valid intervals generated from CSV data")
            return False

        _LOGGER.info(
            "Generated %d intervals. Attempting to program inverter", len(intervals_df)
        )
        try:
            _LOGGER.warning("Intervals_df value is:", intervals_df)
            await self.hass.async_add_executor_job(self._program_inverter, intervals_df)
            _LOGGER.info("Successfully programmed inverter schedule")
            return True
        except Exception as e:
            _LOGGER.error("Failed to program inverter schedule: %s", e)
            return False

    def _program_inverter(self, intervals_df: pd.DataFrame):
        """Blocking function to interact with SellProgrammer."""

        _LOGGER.debug(
            "Connecting to inverter %s (Serial: %s) for programming",
            self.inverter_ip,
            self.inverter_serial,
        )
        inverter_program = SellProgrammer(self.inverter_ip, self.inverter_serial)
        try:
            for index, interval in intervals_df.iterrows():
                mode = interval["mode"]
                start_time = interval["start_time"].strftime("%H:%M")
                stop_time_dt = interval["stop_time"]
                if interval["start_time"] == stop_time_dt:
                    stop_time_dt += timedelta(minutes=1)
                end_time = stop_time_dt.strftime("%H:%M")

                soc = self.maxSoC_percent if mode == "charge" else self.minSoC_percent
                power = (
                    self.peak_charge_power if mode == "charge" else self.inverter_power
                )
                if mode == "idle":
                    power = 1

                _LOGGER.info(
                    f"Programming Interval {index + 1}: {start_time} - {end_time} ({mode}), Power: {power}, SoC: {soc}"
                )
                inverter_program.update_program(
                    index=index,
                    start_t=start_time,
                    stop_t=end_time,
                    soc=soc,
                    power=power,
                    grid_ch=(mode == "charge"),
                    gen_ch=False,
                )

            _LOGGER.debug(inverter_program.show_as_screen())
            _LOGGER.debug("Uploading settings to inverter")
            inverter_program.upload_settings()
            _LOGGER.debug("Settings uploaded")
        except Exception as e:
            _LOGGER.error("Error during inverter programming sequence: %s", e)
            raise
        finally:
            try:
                _LOGGER.debug("Disconnecting from inverter")
                inverter_program.disconnect()
            except Exception as e:
                _LOGGER.warning("Error during SellProgrammer disconnect: %s", e)

    def update_from_config_entry(self, entry: ConfigEntry):
        """Update the inverter instance with new config entry data."""
        self.entry = entry

        self.inverter_ip = entry.options.get(
            "inverter_ip", entry.data.get("inverter_ip")
        )
        self.inverter_serial = entry.options.get(
            "inverter_serial", entry.data.get("inverter_serial")
        )
        self.inverter_power = entry.options.get(
            "inverter_power", entry.data.get("inverter_power")
        )
        self.peak_charge_power = entry.options.get(
            "peak_charge_power", entry.data.get("peak_charge_power")
        )
        self.minSoC_percent = entry.options.get("min_soc", entry.data.get("min_soc"))
        self.maxSoC_percent = entry.options.get("max_soc", entry.data.get("max_soc"))
        _LOGGER.debug("DeyeInverter updated with new config: %s", entry.options)


class DeyeInverter(BaseInverter):
    """Deye specific inverter logic."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        super().__init__(hass, entry)

    def generate_intervals(self):
        """Generate intervals based on P_hybrid_inverter column. Blocking."""
        if self.df is None or self.df.empty:
            _LOGGER.warning("Cannot generate intervals, DataFrame is empty or None")
            return pd.DataFrame()

        if "P_hybrid_inverter" not in self.df.columns:
            _LOGGER.error("Required column 'P_hybrid_inverter' not found in CSV")
            return pd.DataFrame()

        _LOGGER.debug("Generating intervals based on 'P_hybrid_inverter' column")

        def get_mode(p):
            if p > 0:
                return "discharge"
            if p < 0:
                return "charge"
            return "idle"

        try:
            self.df["mode"] = self.df["P_hybrid_inverter"].apply(get_mode)

            intervals = []
            if len(self.df) == 0:
                _LOGGER.warning(
                    "DataFrame is empty after mode calculation (shouldn't happen here)"
                )
                return pd.DataFrame()

            start_time = self.df.iloc[0]["timestamp"]
            current_mode = self.df.iloc[0]["mode"]

            for i in range(1, len(self.df)):
                new_mode = self.df.iloc[i]["mode"]
                timestamp = self.df.iloc[i]["timestamp"]
                prev_timestamp = self.df.iloc[i - 1]["timestamp"]
                if new_mode != current_mode:
                    stop_time = prev_timestamp
                    intervals.append(
                        {
                            "start_time": start_time,
                            "stop_time": stop_time,
                            "mode": current_mode,
                        }
                    )
                    start_time = timestamp
                    current_mode = new_mode
            intervals.append(
                {
                    "start_time": start_time,
                    "stop_time": self.df.iloc[-1]["timestamp"],
                    "mode": current_mode,
                }
            )

            intervals_df = pd.DataFrame(intervals)
            _LOGGER.debug("Raw intervals generated: %d", len(intervals_df))

            intervals_df = intervals_df.head(6)

            if len(intervals_df) < 6:
                _LOGGER.debug("Padding intervals to reach 6.")
                last_stop = intervals_df.iloc[-1]["stop_time"]
                for _ in range(6 - len(intervals_df)):
                    next_start = last_stop + timedelta(minutes=1)
                    next_stop = next_start
                    next_stop += timedelta(minutes=1)

                    intervals_df = pd.concat(
                        [
                            intervals_df,
                            pd.DataFrame(
                                [
                                    {
                                        "start_time": next_start,
                                        "stop_time": next_stop,
                                        "mode": "idle",
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )
                    last_stop = next_stop  # Update for next padding iteration

            _LOGGER.debug(
                "Final intervals generated (padded/limited): %d", len(intervals_df)
            )
            return intervals_df

        except Exception:
            _LOGGER.exception("Error occurred during interval generation:")
            return pd.DataFrame()  # Return empty DF on error

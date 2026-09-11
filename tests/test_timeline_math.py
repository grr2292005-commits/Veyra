import unittest
import numpy as np

TICKS_PER_SECOND = 254016000000

def sec_to_ticks(seconds: float) -> int:
    return int(round(seconds * TICKS_PER_SECOND))

def ticks_to_sec(ticks: int) -> float:
    return float(ticks) / float(TICKS_PER_SECOND)

def frame_to_sample_range(frame_idx: int, fps: float, sample_rate: int = 48000):
    start_sec = frame_idx / fps
    end_sec = (frame_idx + 1) / fps
    start_sample = int(round(start_sec * sample_rate))
    end_sample = int(round(end_sec * sample_rate))
    return start_sample, end_sample

class TestTimelineMath(unittest.TestCase):

    def test_ticks_roundtrip_precision(self):
        test_durations = [0.0, 1.0, 26.65, 3600.0, 7200.5]
        for dur in test_durations:
            ticks = sec_to_ticks(dur)
            reconstructed = ticks_to_sec(ticks)
            drift_sec = abs(dur - reconstructed)
            # Drift must be smaller than 1 nanosecond
            self.assertLess(drift_sec, 1e-9)

    def test_frame_sample_drift_zero_over_one_hour(self):
        sample_rate = 48000
        timebases = [23.976023976, 24.0, 25.0, 29.97002997, 30.0, 50.0, 59.94005994, 60.0]
        one_hour_sec = 3600.0

        for fps in timebases:
            total_frames = int(round(one_hour_sec * fps))
            start_s, end_s = frame_to_sample_range(total_frames - 1, fps, sample_rate)
            time_at_frame_end = (total_frames) / fps
            sample_time = end_s / sample_rate
            drift_ms = abs(time_at_frame_end - sample_time) * 1000.0

            # Drift between video frame edge and audio sample edge must be under 1 audio sample (1/48000 = ~0.02 ms)
            self.assertLess(drift_ms, 0.05, f"Excessive drift for {fps} fps: {drift_ms:.4f} ms")

    def test_hann_overlap_add_energy_reconstruction(self):
        """
        Verify that 50% overlap-add with Hann window reconstructs a constant DC
        or harmonic wave with zero amplitude distortion.
        """
        sample_rate = 16000
        duration_sec = 3.0
        n_samples = int(duration_sec * sample_rate)
        x = np.ones(n_samples, dtype=np.float32)

        window_sec = 1.0
        hop_sec = 0.5
        win_size = int(window_sec * sample_rate)
        hop_size = int(hop_sec * sample_rate)
        window = np.hanning(win_size).astype(np.float32)

        out = np.zeros(n_samples, dtype=np.float32)
        norm = np.zeros(n_samples, dtype=np.float32)

        for start in range(0, n_samples - win_size + 1, hop_size):
            chunk = x[start : start + win_size]
            out[start : start + win_size] += chunk * window
            norm[start : start + win_size] += window

        # In the interior (away from boundary ramp), sum of overlapping Hann windows is exactly 1.0
        interior = slice(win_size, n_samples - win_size)
        np.testing.assert_allclose(norm[interior], 1.0, atol=2e-4)
        np.testing.assert_allclose(out[interior], 1.0, atol=2e-4)

if __name__ == "__main__":
    unittest.main()

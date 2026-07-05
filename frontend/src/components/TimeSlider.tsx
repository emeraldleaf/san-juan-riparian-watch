import { useCallback, useEffect, useRef, useState } from 'react';

interface TimeSliderProps {
  /** ISO date strings in chronological order, e.g. ["2025-07-02", "2025-07-04"]. */
  dates: string[];
  /** Currently selected date (null = "latest" mode). */
  selectedDate: string | null;
  /** Called when the user selects a date or clears selection. */
  onDateChange: (date: string | null) => void;
  /** Whether data is currently loading for the selected date. */
  loading?: boolean;
}

/**
 * A slider control for scrubbing through NDVI acquisition dates.
 * Positioned as an overlay on the map. Includes play/pause for animation.
 */
export default function TimeSlider({
  dates,
  selectedDate,
  onDateChange,
  loading = false,
}: TimeSliderProps) {
  const [playing, setPlaying] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const currentIndex = selectedDate ? dates.indexOf(selectedDate) : -1;

  const stopPlayback = useCallback(() => {
    setPlaying(false);
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const togglePlay = useCallback(() => {
    if (playing) {
      stopPlayback();
      return;
    }
    setPlaying(true);
    // Start from first date if none selected or at the end
    const startIdx = currentIndex < 0 || currentIndex >= dates.length - 1 ? 0 : currentIndex;
    onDateChange(dates[startIdx]);

    let idx = startIdx;
    intervalRef.current = setInterval(() => {
      idx += 1;
      if (idx >= dates.length) {
        stopPlayback();
        return;
      }
      onDateChange(dates[idx]);
    }, 1500);
  }, [playing, currentIndex, dates, onDateChange, stopPlayback]);

  // Cleanup on unmount
  useEffect(() => stopPlayback, [stopPlayback]);

  if (dates.length === 0) return null;

  const handleSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    stopPlayback();
    const idx = Number(e.target.value);
    if (idx < 0) {
      onDateChange(null);
    } else {
      onDateChange(dates[idx]);
    }
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  return (
    <div className="absolute bottom-6 left-6 z-[1000] bg-white rounded-lg shadow-lg px-4 py-3 max-w-sm">
      <div className="flex items-center gap-2 mb-1">
        <button
          onClick={togglePlay}
          className="w-7 h-7 flex items-center justify-center rounded bg-slate-800 text-white text-xs hover:bg-slate-700 transition-colors shrink-0"
          title={playing ? 'Pause' : 'Play timelapse'}
        >
          {playing ? '||' : '\u25B6'}
        </button>
        <span className="text-sm font-semibold text-slate-700">
          {selectedDate ? formatDate(selectedDate) : 'Latest'}
        </span>
        {loading && (
          <span className="text-xs text-slate-400 animate-pulse">Loading...</span>
        )}
        {selectedDate && (
          <button
            onClick={() => { stopPlayback(); onDateChange(null); }}
            className="ml-auto text-xs text-blue-600 hover:text-blue-800"
          >
            Latest
          </button>
        )}
      </div>
      <input
        type="range"
        min={-1}
        max={dates.length - 1}
        value={currentIndex}
        onChange={handleSlider}
        className="w-full accent-slate-800"
      />
      <div className="flex justify-between text-[10px] text-slate-400 mt-0.5">
        <span>Latest</span>
        <span>{formatDate(dates[0])}</span>
        <span>{formatDate(dates[dates.length - 1])}</span>
      </div>
    </div>
  );
}

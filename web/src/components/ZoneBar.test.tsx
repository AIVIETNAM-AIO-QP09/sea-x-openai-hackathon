import { render, screen } from '@testing-library/react';
import type { ZoneBar as ZoneBarData } from '../api/types';
import { computeZoneBar } from '../lib/breakeven';
import { ZoneBar } from './ZoneBar';

// 09 §4 "Ví dụ kiểm tra": same forecast 18–31, two thresholds.
const undetermined: ZoneBarData = {
  axis_label: 'Lượng bán mỗi giờ nếu pause (sp)',
  threshold: 22.5,
  interval: [18, 24, 31],
  verdict: 'undetermined',
  alt_thresholds: [{ label: 'hàng dư 20.000đ', threshold: 16.5 }],
};

describe('ZoneBar (09 §4 examples)', () => {
  it('threshold 22,5 with forecast 18–31 → "Chưa phân định"', () => {
    render(<ZoneBar bar={undetermined} />);
    const img = screen.getByRole('img');
    const label = img.getAttribute('aria-label') ?? '';
    expect(label).toContain('Chưa phân định: khoảng dự báo nằm cả hai phía ngưỡng 22,5 sp/giờ.');
    expect(label).toContain('18–31 sp/giờ (mức giữa 24)');
    expect(label).toContain('Nếu hàng dư 20.000đ: ngưỡng 16,5 sp/giờ.');
    expect(screen.getByText('ngưỡng 22,5')).toBeInTheDocument();
    expect(screen.getByText('hàng dư 20.000đ: 16,5')).toBeInTheDocument();
  });

  it('threshold 16,5 (hàng dư 20.000đ) with the same forecast → "Pause tốt hơn"', () => {
    const bar = computeZoneBar(
      {
        units_left: 120,
        hours_left: 4,
        contribution_per_unit_vnd: 45_000,
        spend_per_hour_vnd: 450_000,
        rate_continue_per_hour: 40,
        pause_rate_interval: [18, 24, 31],
        leftover_value_per_unit_vnd: 20_000,
      },
      [0],
    ).zone_bar;
    expect(bar).not.toBeNull();
    render(<ZoneBar bar={bar as ZoneBarData} estimated />);
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('Pause tốt hơn: cả khoảng dự báo nằm trên ngưỡng.');
    expect(screen.getByText('ngưỡng 16,5')).toBeInTheDocument();
    expect(screen.getByText(/Ước tính nhanh trên trình duyệt/)).toBeInTheDocument();
  });

  it('continue_better reads the third sentence', () => {
    render(<ZoneBar bar={{ ...undetermined, threshold: 3.49, interval: [1.8, 2.4, 3.1], verdict: 'continue_better', alt_thresholds: [] }} />);
    expect(screen.getByText('Tiếp tục tốt hơn: cả khoảng dự báo nằm dưới ngưỡng.')).toBeInTheDocument();
  });
});

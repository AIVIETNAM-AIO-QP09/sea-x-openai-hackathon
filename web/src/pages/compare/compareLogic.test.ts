import type { Recommendation } from '../../api/types';
import { buildSimRequest, flipHits, headline, splitFirstNumber } from './compareLogic';

const rec = {
  recommendation_id: 'rec-1',
  campaign_id: 'CD002',
  status: 'recommend',
  best: { kind: 'schedule_hours', windows_local: [[0, 2], [12, 14]] },
  runner_up: { kind: 'continue' },
  p_best_beats_runner_up: 0.99,
  expected_gain_vnd: 4_300_000,
  zone_bar: null,
  flip_conditions: [{ factor: 'restock_delay_days', flip_at: -1, text: 'x' }],
  confidence: 'reference',
  reasons: [],
  inputs_ref: { forecast_ids: [], estimate_id: 'ie', param_version: 1, goal_id: 'g', data_as_of: '2026-11-11T01:00:00+07:00' },
} satisfies Recommendation;

describe('compareLogic', () => {
  it('picks the figure with a unit, not the event name', () => {
    expect(splitFirstNumber('Ở giá 11.11 mỗi nồi chỉ lãi 9.280đ')?.number).toBe('9.280đ');
    expect(splitFirstNumber('Hàng sẽ hết khoảng 13:00: ads không bán thêm')?.number).toBe('13:00');
    expect(splitFirstNumber('vẫn bán khoảng 18–31 sp/giờ')?.number).toBe('18–31 sp/giờ');
    expect(splitFirstNumber('Không được tắt hẳn')).toBeNull();
  });

  it('headline in Vietnamese with the gain in millions', () => {
    expect(headline(rec)).toBe('Chỉ chạy 0–2h, 12–14h. Lợi hơn tiếp tục khoảng 4,3 triệu đ.');
    expect(headline({ ...rec, status: 'none_meets_goal' })).toBeNull();
  });

  it('flip on restock only when the slider crosses flip_at in its direction', () => {
    expect(flipHits(rec, { leftoverValue: null, restockDelayDays: 0 })).toHaveLength(0);
    expect(flipHits(rec, { leftoverValue: null, restockDelayDays: 2 })).toHaveLength(0);
    expect(flipHits(rec, { leftoverValue: null, restockDelayDays: -1 })).toHaveLength(1);
  });

  it('builds a SimRequest with 05 §3 parameter keys and the next whole hour as start', () => {
    const body = buildSimRequest(undefined, rec, { leftoverValue: 20_000, restockDelayDays: -1 }, 300);
    expect(body).toMatchObject({
      campaign_id: 'CD002',
      goal_id: 'g',
      start: '2026-11-10T18:00:00.000Z',
      samples: 300,
      seed: 20261111,
      param_overrides: { leftover_value_per_unit: 20_000, restock_delay_days: -1 },
    });
  });
});

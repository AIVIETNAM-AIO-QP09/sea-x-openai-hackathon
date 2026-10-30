import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import { routes } from '../../routes';

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(() => {
  window.localStorage.clear();
});

describe('Compare screen · CD002 on 11.11 (fixture)', () => {
  it('tier 1: conclusion, zone bar, "better than both" line and blocked pause card', async () => {
    renderAt('/sku/NOICHIEN2L/compare');
    expect(
      await screen.findByText('Chỉ chạy 0–2h, 12–14h. Lợi hơn tiếp tục khoảng 4,3 triệu đ.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 1, name: 'So sánh lựa chọn cho chiến dịch CD002' })).toBeInTheDocument();
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('Pause tốt hơn');
    expect(await screen.findByText('Pause tốt hơn tiếp tục, nhưng không được tắt hẳn vì cam kết flash sale.')).toBeInTheDocument();
    expect(screen.getByText('Phương án tốt hơn cả hai: Chỉ chạy 0–2h, 12–14h.')).toBeInTheDocument();

    const cards = within(screen.getByRole('list', { name: 'Năm hành động' })).getAllByRole('listitem', { name: undefined });
    const top = cards.filter((li) => li.parentElement?.getAttribute('aria-label') === 'Năm hành động');
    expect(top).toHaveLength(5);
    const pause = top.find((li) => li.textContent?.startsWith('Tạm dừng') && !li.textContent.includes('hàng về'));
    expect(pause).toHaveTextContent('Không làm được');
    expect(pause).toHaveTextContent('Vi phạm cam kết flash sale');
    const best = top.find((li) => li.textContent?.includes('Đề xuất'));
    expect(best).toHaveTextContent('Chỉ chạy 0–2h, 12–14h');
  });

  it('tier 2: reasons with clickable numbers and the flip condition', async () => {
    renderAt('/campaign/CD002/compare');
    await userEvent.click(await screen.findByRole('button', { name: 'Vì sao?' }));
    const chip = screen.getByRole('button', { name: /9\.280đ/ });
    await userEvent.click(chip);
    expect(screen.getByRole('dialog', { name: 'Nguồn: Đóng góp NOICHIEN2L' })).toBeInTheDocument();
    expect(screen.getByText('Nếu hàng về trong hôm nay, chạy tiếp có lợi hơn')).toBeInTheDocument();

    // Restock slider: moving to "sớm 1 ngày" reaches the flip point (fixture estimate).
    const slider = screen.getByLabelText(/Hàng về trễ/);
    fireEvent.change(slider, { target: { value: '-1' } });
    expect(screen.getByText(/đã chạm điểm đổi: Nếu hàng về trong hôm nay/)).toBeInTheDocument();
  });

  it('tier 3: table of 5 actions with violations, and lineage', async () => {
    renderAt('/campaign/CD002/compare');
    await userEvent.click(await screen.findByRole('button', { name: 'Chi tiết kiểm tra' }));
    const table = await screen.findByRole('table', { name: 'Kết quả 5 hành động trong kỳ quyết định' });
    const rows = within(table).getAllByRole('row');
    expect(rows).toHaveLength(6);
    expect(within(table).getAllByText('Vi phạm cam kết flash sale')).toHaveLength(2);
    expect(within(table).getByText('−4.480.000đ')).toBeInTheDocument();
    expect(screen.getByText('fc-8812, fc-8813, fc-8814')).toBeInTheDocument();
    expect(screen.getByText('ie-37')).toBeInTheDocument();
    expect(screen.getByText('1.000 · 20261111')).toBeInTheDocument();
  });

  it('decision form is disabled in fixture mode with the reason shown', async () => {
    renderAt('/campaign/CD002/compare');
    await userEvent.click(await screen.findByRole('button', { name: 'Tạo quyết định' }));
    const form = screen.getByRole('form', { name: 'Tạo quyết định' });
    const save = within(form).getByRole('button', { name: 'Lưu bản nháp quyết định' });
    expect(save).toBeDisabled();
    expect(within(form).getByText(/Chế độ dữ liệu mẫu: chưa gửi được/)).toBeInTheDocument();
    expect(within(form).getByRole('radio', { name: /^Tạm dừng · Vi phạm cam kết flash sale/ })).toBeDisabled();
    expect(within(form).getByRole('radio', { name: 'Chỉ chạy 0–2h, 12–14h' })).toBeChecked();
  });
});

describe('Compare screen · two more ZoneBar examples (fixture)', () => {
  it('normal day: continue wins', async () => {
    renderAt('/campaign/CD002/compare?rec=rec-540');
    expect(await screen.findByText('Tiếp tục. Lợi hơn giảm ngân sách 30% khoảng 0,51 triệu đ.')).toBeInTheDocument();
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('Tiếp tục tốt hơn');
    expect(screen.queryByText(/Phương án tốt hơn cả hai/)).not.toBeInTheDocument();
  });

  it('page-10 example: 22,5 undetermined → drag leftover value to 20.000đ → 16,5 pause better', async () => {
    renderAt('/campaign/VIDU-T10/compare?rec=rec-510');
    expect(await screen.findByText(/Chưa phân định giữa tạm dừng và tiếp tục/)).toBeInTheDocument();
    expect(screen.getByText('Kết quả dựa trên giả định, chưa phải dự báo đã kiểm.')).toBeInTheDocument();
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('ngưỡng 22,5 sp/giờ');

    await userEvent.click(screen.getByRole('button', { name: 'Vì sao?' }));
    fireEvent.change(screen.getByLabelText(/1 sp còn lại sau hạn/), { target: { value: '20000' } });

    const label = screen.getByRole('img').getAttribute('aria-label') ?? '';
    expect(label).toContain('Pause tốt hơn: cả khoảng dự báo nằm trên ngưỡng.');
    expect(label).toContain('Ngưỡng hòa vốn 16,5 sp/giờ');
    expect(screen.getByText(/Ước tính nhanh trên trình duyệt/)).toBeInTheDocument();
    expect(screen.getByText(/đã chạm điểm đổi: Nếu hàng dư còn giá trị từ 16\.875đ/)).toBeInTheDocument();
  });
});

describe('Compare entry and overview link', () => {
  it('/compare lists active recommendations and the illustrative cases', async () => {
    renderAt('/compare');
    expect(await screen.findByText('Ví dụ minh họa (dữ liệu mẫu)')).toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: /Mở so sánh/ }).map((a) => a.getAttribute('href'));
    expect(links).toEqual(
      expect.arrayContaining(['/campaign/CD002/compare', '/campaign/CD002/compare?rec=rec-540', '/campaign/VIDU-T10/compare?rec=rec-510']),
    );
  });

  it('overview "So sánh" opens the compare screen for the SKU', async () => {
    const router = renderAt('/');
    const attention = await screen.findByRole('region', { name: /Cần xem ngay/ });
    const card = within(attention).getByText('Nồi chiên không dầu mini 2L').closest('li') as HTMLElement;
    await userEvent.click(within(card).getByRole('link', { name: /So sánh/ }));
    expect(router.state.location.pathname).toBe('/sku/NOICHIEN2L/compare');
    expect(await screen.findByText(/Lợi hơn tiếp tục khoảng 4,3 triệu đ/)).toBeInTheDocument();
  });
});

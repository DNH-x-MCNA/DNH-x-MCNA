// Một nguồn nhãn duy nhất cho mọi nơi hiển thị/chọn vai trò trong frontend.
// Mã role vẫn giữ nguyên để trao đổi với backend; chỉ lớp giao diện dùng nhãn tiếng Việt.
export const ROLE_LABELS: Record<string, string> = {
  admin_ops: "Admin Vận Hành (Hệ thống)",
  c_level: "Tổng Giám Đốc (C-Level)",
  regional_director: "Giám đốc Miền / Kênh (Trưởng phòng)",
  qlv: "Quản lý Vùng (QLV)",
};

export function getRoleLabel(role: string): string {
  return ROLE_LABELS[role] || role;
}

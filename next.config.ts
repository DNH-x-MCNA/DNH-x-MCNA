import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 28/09/2026: ban deploy #133 tren Vercel tro toi file CSS cu (cua truoc #133) - thieu toan bo token
  // mau nen nut chinh trong suot, vien/chu nhat - trong khi JS la ban moi. Next 16.3 bat mac dinh ca hai
  // co che duoi day va ca hai deu co the giu lai CSS cu qua cac lan deploy:
  // - supportsImmutableAssets: file tinh nam o /_next/static/immutable/*, dung CHUNG giua cac ban deploy
  //   va chi nhan dien bang ten file (ETag = duong dan). Tat -> moi ban deploy phuc vu file cua chinh no.
  // - turbopackFileSystemCacheForBuild: Vercel khoi phuc .next/cache giua cac lan build. Tat -> moi lan
  //   deploy bien dich lai CSS tu dau (app nho, build lau hon vai chuc giay).
  // scripts/kiem_css_sau_build.mjs chan build neu CSS da build khong khop globals.css hien tai.
  supportsImmutableAssets: false,
  experimental: {
    turbopackFileSystemCacheForBuild: false,
  },
};

export default nextConfig;

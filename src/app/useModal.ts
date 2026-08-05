"use client";

import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Hanh vi modal toi thieu dung chung cho moi dialog trong app (05/08/2026):
 * - Escape dong modal
 * - Bay focus (Tab/Shift+Tab khong thoat ra ngoai modal)
 * - Khoa cuon nen trong luc modal mo
 * - Tu dong focus vao modal khi mo, tra focus ve nut da mo modal khi dong
 *
 * `active`: true khi modal dang hien (component goi hook nay co the luon mounted
 * hoac chi mounted khi mo - ca hai deu dung duoc, chi can truyen dung trang thai).
 */
export function useModal(active: boolean, onClose: () => void) {
  const containerRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);
  // Giu ham onClose moi nhat qua ref, KHONG dua vao dependency array cua effect ben duoi. Neu
  // component cha truyen onClose dang inline arrow function (rat pho bien, vd
  // "() => setOpen(false)"), no se bi tao lai moi lan render - neu dua vao deps, moi lan nguoi
  // dung go chu trong 1 input KIEM SOAT (controlled input) trong modal se lam component cha
  // re-render, tao onClose moi, kich hoat lai effect va CUOP FOCUS ve phan tu focusable dau tien
  // (thuong la nut dong "X") ngay giua luc dang go - bug thuc te da gap 05/08/2026.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!active) return;

    previousFocusRef.current = document.activeElement as HTMLElement | null;
    const container = containerRef.current;
    const focusables = container?.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
    (focusables && focusables[0] ? focusables[0] : container)?.focus();

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key !== "Tab" || !containerRef.current) return;
      const nodes = containerRef.current.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR);
      if (nodes.length === 0) return;
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown, true);
    return () => {
      document.removeEventListener("keydown", handleKeyDown, true);
      document.body.style.overflow = prevOverflow;
      previousFocusRef.current?.focus?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return containerRef;
}

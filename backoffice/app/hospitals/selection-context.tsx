"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { Hospital } from "@/lib/api";

type HospitalSelectionContextValue = {
  /** Checked hospital ids. */
  selected: Set<number>;
  /** Checked hospital objects, kept so the schedule modal has names/timezone. */
  picked: Map<number, Hospital>;
  /** Add the hospital to the selection, or remove it if already checked. */
  toggle: (hospital: Hospital) => void;
  /** Select or deselect a batch at once (e.g. "select all on this page"). */
  setMany: (hospitals: Hospital[], selected: boolean) => void;
  /** Drop the whole selection. */
  clear: () => void;
};

const HospitalSelectionContext =
  createContext<HospitalSelectionContextValue | null>(null);

/**
 * Holds the Hospitals-list multi-select. Mounted by `app/hospitals/layout.tsx`,
 * which the list page and the hospital detail page share — so the selection
 * survives navigating into a hospital and back (a shared segment layout does
 * not remount on navigation).
 */
export function HospitalSelectionProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [picked, setPicked] = useState<Map<number, Hospital>>(new Map());

  const toggle = useCallback((hospital: Hospital) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(hospital.id)) next.delete(hospital.id);
      else next.add(hospital.id);
      return next;
    });
    setPicked((prev) => {
      const next = new Map(prev);
      if (next.has(hospital.id)) next.delete(hospital.id);
      else next.set(hospital.id, hospital);
      return next;
    });
  }, []);

  const setMany = useCallback((hospitals: Hospital[], select: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const h of hospitals) {
        if (select) next.add(h.id);
        else next.delete(h.id);
      }
      return next;
    });
    setPicked((prev) => {
      const next = new Map(prev);
      for (const h of hospitals) {
        if (select) next.set(h.id, h);
        else next.delete(h.id);
      }
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setSelected(new Set());
    setPicked(new Map());
  }, []);

  const value = useMemo(
    () => ({ selected, picked, toggle, setMany, clear }),
    [selected, picked, toggle, setMany, clear]
  );

  return (
    <HospitalSelectionContext.Provider value={value}>
      {children}
    </HospitalSelectionContext.Provider>
  );
}

export function useHospitalSelection(): HospitalSelectionContextValue {
  const ctx = useContext(HospitalSelectionContext);
  if (!ctx) {
    throw new Error(
      "useHospitalSelection must be used within a HospitalSelectionProvider"
    );
  }
  return ctx;
}

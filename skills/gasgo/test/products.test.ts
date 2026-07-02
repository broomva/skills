import { expect, test } from "bun:test";
import { normalizeProduct } from "../src/products.ts";

test("biodiesel is not misclassified as diesel", () => {
  // "BIODIESEL" contains the substring "DIESEL"; the classifier must check
  // BIODIESEL first or it silently reclassifies biodiesel as ACPM/diesel.
  // (Observed: 533 "BIODIESEL EXTRA" rows in gjy9-tpph.)
  expect(normalizeProduct("BIODIESEL")).toBe("BIODIESEL");
  expect(normalizeProduct("BIODIESEL EXTRA")).toBe("BIODIESEL");
  expect(normalizeProduct("biodiesel b10")).toBe("BIODIESEL");
});

test("diesel / ACPM still classify correctly", () => {
  expect(normalizeProduct("ACPM - DIESEL")).toBe("ACPM_DIESEL");
  expect(normalizeProduct("DIESEL")).toBe("ACPM_DIESEL");
  expect(normalizeProduct("DIÉSEL")).toBe("ACPM_DIESEL");
  expect(normalizeProduct("acpm")).toBe("ACPM_DIESEL");
});

test("gasoline variants classify by grade", () => {
  expect(normalizeProduct("GASOLINA CORRIENTE OXIGENADA")).toBe("GASOLINA_CORRIENTE");
  expect(normalizeProduct("GASOLINA EXTRA OXIGENADA")).toBe("GASOLINA_EXTRA");
  expect(normalizeProduct("corriente")).toBe("GASOLINA_CORRIENTE");
});

test("GNCV aliases classify to GNCV", () => {
  expect(normalizeProduct("GNCV")).toBe("GNCV");
  expect(normalizeProduct("GNV")).toBe("GNCV");
  expect(normalizeProduct("gas")).toBe("GNCV");
});

test("unknown product returns null", () => {
  expect(normalizeProduct("")).toBeNull();
  expect(normalizeProduct("kerosene")).toBeNull();
});

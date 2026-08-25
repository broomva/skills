import { expect, test, describe } from "bun:test";
import { extractItems, parsePriceCents } from "../src/parse.ts";

describe("parsePriceCents", () => {
  test("parses plain prices", () => {
    expect(parsePriceCents("$2.99")).toBe(299);
    expect(parsePriceCents("2.99")).toBe(299);
    expect(parsePriceCents("$15.49")).toBe(1549);
    expect(parsePriceCents("$0.56")).toBe(56);
  });

  test("strips thousands separators", () => {
    expect(parsePriceCents("$1,299.00")).toBe(129900);
  });

  // Multi-buy copy must NOT parse as a unit price — "Buy 2 for $6" is not a $6 item.
  test("rejects multi-buy and other non-price labels", () => {
    expect(parsePriceCents("Buy 2 for $6")).toBeNull();
    expect(parsePriceCents("2 for $5.00")).toBeNull();
    expect(parsePriceCents("")).toBeNull();
    expect(parsePriceCents(null)).toBeNull();
    expect(parsePriceCents("Sale")).toBeNull();
  });
});

const itemNode = (over: Record<string, unknown> = {}) => ({
  id: "items_24999-3428150",
  name: "Smithfield Naturally Hickory Smoked Thick Cut Bacon",
  size: "12 oz",
  productId: "3428150",
  brandName: "smithfield",
  evergreenUrl: "3428150-smithfield-bacon-12-oz",
  price: {
    __typename: "ItemsItemPrice",
    viewSection: {
      priceString: "$2.99",
      fullPriceString: "$6.99",
      pricePerUnitString: "$0.25/oz",
      badge: { offerLabelString: "57% off" },
    },
  },
  ...over,
});

describe("extractItems", () => {
  test("pulls items out of an arbitrarily nested response", () => {
    const data = { a: { b: [{ c: { collection: { items: [itemNode()] } } }] } };
    const items = extractItems(data);
    expect(items).toHaveLength(1);
    const i = items[0];
    expect(i.name).toContain("Bacon");
    expect(i.priceCents).toBe(299);
    expect(i.fullPriceCents).toBe(699);
    expect(i.brand).toBe("smithfield");
    expect(i.size).toBe("12 oz");
    expect(i.url).toContain("3428150-smithfield-bacon-12-oz");
  });

  test("derives percentOff from prices, not from the label", () => {
    // 299/699 => 57.2% => 57. Independent of offerLabelString.
    expect(extractItems({ x: itemNode() })[0].percentOff).toBe(57);
  });

  test("percentOff is null when there is no discount", () => {
    const node = itemNode({
      price: {
        __typename: "ItemsItemPrice",
        viewSection: { priceString: "$15.49", fullPriceString: null, badge: null },
      },
    });
    const i = extractItems({ x: node })[0];
    expect(i.priceCents).toBe(1549);
    expect(i.percentOff).toBeNull();
  });

  test("keeps a multi-buy offer label even when it has no numeric price", () => {
    const node = itemNode({
      productId: "999",
      price: {
        __typename: "ItemsItemPrice",
        viewSection: { priceString: "$5.49", badge: { offerLabelString: "Buy 2 for $6" } },
      },
    });
    const i = extractItems({ x: node })[0];
    expect(i.offerLabel).toBe("Buy 2 for $6");
    expect(i.percentOff).toBeNull();
  });

  test("deduplicates the same product appearing under several collections", () => {
    const data = { featured: [itemNode()], grid: [itemNode()], carousel: [itemNode()] };
    expect(extractItems(data)).toHaveLength(1);
  });

  test("ignores nodes that merely have a name", () => {
    expect(extractItems({ collection: { name: "On Sale", slug: "x" } })).toHaveLength(0);
  });
});

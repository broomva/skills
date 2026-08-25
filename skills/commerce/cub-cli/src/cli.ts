#!/usr/bin/env bun
import { deals, saleCollections, search, collection } from "./engine.ts";
import { harvestFromHar } from "./harvest.ts";
import { provenance, registry, saveHarvested } from "./ops.ts";
import { bootstrap, parseCookieHeader, saveSession } from "./session.ts";
import * as store from "./store.ts";
import type { Item } from "./parse.ts";
import { GraphQLError } from "./client.ts";

const args = process.argv.slice(2);
const cmd = args[0];
const flag = (name: string): string | undefined => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : undefined;
};
const has = (name: string) => args.includes(`--${name}`);
const json = has("json");

const money = (c: number | null) => (c === null ? "" : `$${(c / 100).toFixed(2)}`);

function printItems(items: Item[]) {
  if (json) return console.log(JSON.stringify(items, null, 2));
  if (!items.length) return console.log("no items");
  for (const i of items) {
    const price = (i.priceLabel ?? money(i.priceCents)).padStart(8);
    const was = i.fullPriceLabel ? ` was ${i.fullPriceLabel}` : "";
    const off = i.percentOff ? ` (${i.percentOff}% off)` : i.offerLabel ? ` (${i.offerLabel})` : "";
    const size = i.size ? `  ${i.size}` : "";
    console.log(`${price}${off}  ${i.name}${size}${was}`);
  }
  console.log(`\n${items.length} item(s)`);
}

const HELP = `cub — CLI for the Cub storefront (Instacart Storefront Pro)

  cub deals [--min-off N] [--limit N] [--slug S]   items on sale, deepest discount first
  cub collections                                  browsable collections (department nav)
  cub browse --slug <slug> [--limit N]             items in a collection
  cub search <term> [--limit N]                    search (see note below)
  cub watch add <productId> --below <price>        watch a product
  cub watch list                                   list watches
  cub watch check                                  refresh prices, report triggers
  cub harvest --har <file.har>                     add operations from a DevTools HAR
  cub ops                                          show callable operations
  cub auth import                                  paste your browser Cookie: header
  cub auth guest                                   mint a fresh guest session

  --json    machine-readable output

Notes
  Reads run on an automatically minted guest session; no login required.
  Account operations (cart, lists, orders) need 'cub auth import'.
  The API accepts only persisted queries, so this client can call exactly the
  operations whose hashes have been observed. 'cub harvest' adds more.`;

async function main() {
  switch (cmd) {
    case "deals": {
      const items = await deals({
        minOff: flag("min-off") ? Number(flag("min-off")) : undefined,
        limit: flag("limit") ? Number(flag("limit")) : undefined,
        slug: flag("slug"),
      });
      printItems(items);
      break;
    }
    case "collections": {
      const cs = await saleCollections();
      if (json) console.log(JSON.stringify(cs, null, 2));
      else cs.forEach((c) => console.log(`${c.slug}\n    ${c.name}`));
      break;
    }
    case "browse": {
      const slug = flag("slug");
      if (!slug) throw new Error("browse needs --slug (see `cub collections`)");
      printItems(await collection(slug, flag("limit") ? Number(flag("limit")) : 30));
      break;
    }
    case "search": {
      const term = args[1];
      if (!term || term.startsWith("--")) throw new Error("search needs a term");
      const res = await search(term, flag("limit") ? Number(flag("limit")) : 25);
      if (res.degraded && !json) {
        console.error(
          `note: no search operation has been harvested yet, so this filtered the\n` +
            `      "${res.searchedCollection}" collection locally rather than searching the\n` +
            `      whole store. Results are incomplete. To enable real search:\n` +
            `      run a search on cub.com with DevTools open, save the Network tab as HAR,\n` +
            `      then: cub harvest --har <file.har>\n`,
        );
      }
      printItems(res.items);
      break;
    }
    case "harvest": {
      const file = flag("har");
      if (!file) throw new Error("harvest needs --har <file.har>");
      const har = await Bun.file(file).json();
      const r = harvestFromHar(har);
      const names = Object.keys(r.operations);
      if (!names.length) {
        console.log(`scanned ${r.scanned} graphql entr(ies), found no persisted-query hashes.`);
        break;
      }
      await saveHarvested(r.operations);
      console.log(`harvested ${names.length} operation(s) from ${r.scanned} graphql entr(ies):`);
      names.forEach((n) => console.log(`  ${n}`));
      break;
    }
    case "ops": {
      const reg = await registry();
      const names = Object.keys(reg).sort();
      if (json) console.log(JSON.stringify(reg, null, 2));
      else {
        console.log(`${names.length} callable operation(s):\n`);
        names.forEach((n) => console.log(`  ${n}  [${reg[n].capturedFrom}]`));
        console.log(`\nprovenance: ${provenance().method}`);
      }
      break;
    }
    case "watch": {
      const db = store.open();
      const sub = args[1];
      if (sub === "add") {
        const pid = args[2];
        const below = flag("below");
        if (!pid) throw new Error("watch add needs a productId");
        store.addWatch(db, pid, flag("name") ?? pid, below ? Math.round(Number(below) * 100) : null);
        console.log(`watching ${pid}${below ? ` below $${below}` : ""}`);
      } else if (sub === "list") {
        const rows = store.listWatches(db);
        if (json) console.log(JSON.stringify(rows, null, 2));
        else rows.forEach((r) => console.log(`${r.productId}  ${r.name}  ${money(r.targetCents)}`));
      } else if (sub === "check") {
        const items = await deals({ limit: 60 });
        const n = store.record(db, items);
        const hits = store.triggered(db);
        console.log(`recorded ${n} price point(s)`);
        if (json) console.log(JSON.stringify(hits, null, 2));
        else if (!hits.length) console.log("no watches triggered");
        else hits.forEach((h) => console.log(`HIT  ${h.name}  ${money(h.priceCents)} <= ${money(h.targetCents)}`));
      } else throw new Error("watch: use add | list | check");
      break;
    }
    case "auth": {
      const sub = args[1];
      if (sub === "guest") {
        const jar = await bootstrap();
        console.log(`guest session minted (${Object.keys(jar).length} cookies)`);
      } else if (sub === "import") {
        console.error("Paste your Cookie: header for www.cub.com, then press Ctrl-D:");
        const header = await Bun.stdin.text();
        const jar = parseCookieHeader(header.trim());
        if (!Object.keys(jar).length) throw new Error("no cookies parsed");
        await saveSession(jar);
        console.log(`imported ${Object.keys(jar).length} cookie(s)`);
      } else throw new Error("auth: use import | guest");
      break;
    }
    case "help":
    case "--help":
    case undefined:
      console.log(HELP);
      break;
    default:
      console.error(`unknown command: ${cmd}\n`);
      console.log(HELP);
      process.exit(2);
  }
}

main().catch((e) => {
  console.error(e instanceof GraphQLError || e instanceof Error ? e.message : String(e));
  process.exit(1);
});

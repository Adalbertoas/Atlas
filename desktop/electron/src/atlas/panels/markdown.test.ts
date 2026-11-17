import { strict as assert } from "node:assert";
import { test } from "node:test";
import { parseInline, parseMarkdown } from "./markdown.ts";

test("negrita, cursiva, código y enlaces", () => {
  assert.deepEqual(parseInline("Hola **mundo** y *tú* con `x=1`"), [
    { type: "text", text: "Hola " },
    { type: "bold", children: [{ type: "text", text: "mundo" }] },
    { type: "text", text: " y " },
    { type: "italic", children: [{ type: "text", text: "tú" }] },
    { type: "text", text: " con " },
    { type: "code", text: "x=1" },
  ]);
  assert.deepEqual(parseInline("ver [docs](https://example.com/a)."), [
    { type: "text", text: "ver " },
    { type: "link", text: "docs", href: "https://example.com/a" },
    { type: "text", text: "." },
  ]);
  // URL suelta sin el punto final.
  assert.deepEqual(parseInline("en https://example.com."), [
    { type: "text", text: "en " },
    { type: "link", text: "https://example.com", href: "https://example.com" },
    { type: "text", text: "." },
  ]);
});

test("los enlaces que no son http no se convierten", () => {
  const parsed = parseInline("[x](javascript:alert(1))");
  assert.ok(parsed.every((node) => node.type !== "link"));
});

test("un asterisco suelto no abre cursiva", () => {
  assert.deepEqual(parseInline("5 * 3 = 15"), [{ type: "text", text: "5 * 3 = 15" }]);
});

test("bloques: título, listas, código y párrafos", () => {
  const blocks = parseMarkdown("## Clima\nHoy:\n- soleado\n- 30°\n\n1. uno\n2. dos\n```py\nprint(1)\n```\nFin");
  assert.deepEqual(blocks.map((b) => b.type), ["heading", "paragraph", "list", "list", "code", "paragraph"]);
  const lists = blocks.filter((b) => b.type === "list");
  assert.equal(lists[0].type === "list" && lists[0].items.length, 2);
  assert.equal(lists[1].type === "list" && lists[1].ordered, true);
  const code = blocks.find((b) => b.type === "code");
  assert.deepEqual(code, { type: "code", language: "py", text: "print(1)" });
});

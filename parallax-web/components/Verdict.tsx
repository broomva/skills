/**
 * `.verdict` is a flex row: the VERDICT label is a ::before, and the body is
 * the second item. A bare text node works, but any inline element inside it --
 * a <code>, an <a> -- becomes a flex item of its own and shrinks to its
 * minimum content width, which renders a code span one character per line.
 *
 * The body gets exactly one wrapper so the row always has exactly two items.
 */
export function Verdict({ children }: { children: React.ReactNode }) {
  return (
    <p className="verdict">
      <span>{children}</span>
    </p>
  );
}

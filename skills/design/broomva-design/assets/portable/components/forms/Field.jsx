import React from "react";

function mergeIds(...values) {
  return [...new Set(values.flatMap((value) => String(value || "").split(/\s+/)).filter(Boolean))]
    .join(" ") || undefined;
}

/* Accessible label + one control + one hint/error line. The control inherits
   the field relationship so callers cannot accidentally strand visible copy. */
export function Field({
  id,
  hintId,
  errorId,
  label,
  hint,
  error,
  children,
  style,
}) {
  const generatedControlId = React.useId();
  const generatedHintId = React.useId();
  const generatedErrorId = React.useId();
  const isControl = React.isValidElement(children);
  const childProps = isControl ? children.props : {};
  const controlId = childProps.id || id || generatedControlId;
  const descriptionId = error
    ? (errorId || `${generatedErrorId}-error`)
    : hint
      ? (hintId || `${generatedHintId}-hint`)
      : undefined;
  const control = isControl
    ? React.cloneElement(children, {
        id: controlId,
        "aria-describedby": mergeIds(childProps["aria-describedby"], descriptionId),
        "aria-invalid": error ? true : childProps["aria-invalid"],
      })
    : children;

  React.useEffect(() => {
    if (
      !isControl &&
      typeof process !== "undefined" &&
      process.env?.NODE_ENV !== "production"
    ) {
      console.warn("Broomva Field expects exactly one React element as its control.");
    }
  }, [isControl]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6, ...style }}>
      {label && (
        <label
          htmlFor={controlId}
          style={{ fontSize: 13, fontWeight: 500, color: "var(--foreground)" }}
        >
          {label}
        </label>
      )}
      {control}
      {error ? (
        <span id={descriptionId} style={{ fontSize: 12, color: "var(--bv-danger)" }}>
          {error}
        </span>
      ) : hint ? (
        <span id={descriptionId} style={{ fontSize: 12, color: "var(--muted-foreground)" }}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

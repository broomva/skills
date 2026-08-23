/**
 * Where the source actually lives. Parallax is the ontology simulation layer of
 * the bstack, so the runtime is a directory inside the skills monorepo rather
 * than a repository of its own. That makes the clone target and the source tree
 * two different strings, and every link on the site has to pick the right one:
 * cloning REPO would fail, and pointing "read the source" at CLONE would land a
 * reader on a monorepo root that says nothing about Parallax.
 */
export const CLONE = "https://github.com/broomva/skills";
export const RUNTIME = "skills/simulation/parallax/runtime";
export const REPO = `${CLONE}/tree/main/${RUNTIME}`;

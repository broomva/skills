// Liquid Midnight · liquid-metal ASCII background as a pen.dev shader fill.
// The kit's metalFlow (kit/ascii.js; deck/index.html @187972f line 1564) evaluated per cell; the value picks a glyph from the
// baked ramp ' .·:-=+*%#@' (ascii-atlas.png, 11 glyphs). Capped at .72 so the heaviest glyphs never appear; low alpha.
precision highp float;
/** @resolution */
uniform vec2 u_resolution;
/** @time */
uniform float u_time;
/** @label Glyph atlas */
uniform sampler2D u_atlas;
/**
 * @label Glyph colour
 * @color
 * @default #a8c4e8
 */
uniform vec3 u_color;
/**
 * @label Ground colour
 * @color
 * @default #040d18
 */
uniform vec3 u_ground;
/**
 * @label Glyph alpha (.15 night, .12 day)
 * @default 0.15
 * @range 0, 1
 */
uniform float u_alpha;
/**
 * @label Cell (px)
 * @default 15
 * @range 6, 40
 */
uniform float u_cell;
void main() {
  vec2 px = vec2(gl_FragCoord.x, u_resolution.y - gl_FragCoord.y);
  vec2 cell = floor(px / u_cell);
  vec2 c = cell * u_cell;
  float t = u_time;
  float f = sin(c.x * .011 + sin(c.y * .008 + t * .19) * 1.7 + t * .13) * .5 + .5;
  float g = sin(c.y * .015 - t * .11 + sin(c.x * .005 + t * .07) * 2.2) * .5 + .5;
  float v = min(.72, pow(f * g, 2.2) * 1.25);
  float idx = v <= .02 ? 0. : min(10., 1. + floor(v * 10.));
  // the kit draws an 11px glyph (7 px wide) at the top-left of each 15px cell; the baked atlas cell is 28 x 53, so the
  // glyph box is 7/15 of the cell wide and (7/15)/(28/53) tall: atlas proportions, no stretching
  vec2 local = (px - c) / (u_cell * vec2(7. / 15., (7. / 15.) * (53. / 28.)));
  float inside = step(local.x, 1.) * step(local.y, 1.);
  vec2 uv = vec2((idx + clamp(local.x, 0., 1.)) / 11., 1. - clamp(local.y, 0., 1.));
  float a = texture2D(u_atlas, uv).a * u_alpha * inside;
  gl_FragColor = vec4(mix(u_ground, u_color, a), 1.);
}

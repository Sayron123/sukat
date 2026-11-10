import type { Category } from "@/lib/types";

const RULES: [Category, RegExp][] = [
  ["Paint", /\b(boysen|davies|paints?|pintura|enamel|latex|primer|thinner|varnish|barnis|lacquer|emulsion|neutralizer|elastomeric|tinting|sandpaper|liha|masking)\b/i],
  ["Electrical", /\b(electrical|thhn|pdx|breakers?|outlet|conduit|bulb|led|junction box|utility box|panel board)\b/i],
  ["Nails & Screws", /\b(nails?|pako|screws?|tekscrews?|rivets?|bolts?|wall plug)\b/i],
  ["Plumbing", /\b(plumbing|faucet|valve|teflon|sanitary|ppr|gi pipe|pressure pipe|pvc (pipe|elbow|tee|coupling)|solvent cement|floor drain|garden hose|shower head|water closet)\b/i],
  ["Roofing", /\b(roofing|yero|gutter|flashing|long span|ridge roll|gi sheet)\b/i],
  ["Steel", /\b(deformed bar|rebar|bakal|angle bar|flat bar|tubular|purlins?|tie wire|cyclone wire|welding rod)\b/i],
  ["Wood", /\b(plywood|lumber|kahoy|phenolic|gypsum board|fiber cement board)\b/i],
  ["Cement", /\b(portland|white cement|semento|tile (adhesive|grout)|skim coat|hollow blocks?|chb|washed sand|fine sand|gravel|graba|escombro|hydrated lime)\b/i],
  ["Tools", /\b(hammer|martilyo|hand saw|hacksaw|lagari|measuring tape|spirit level|trowel|shovel|wheelbarrow|pliers|screwdriver|cutting disc|grinding disc|chisel|steel brush|cutter knife)\b/i],
];

export function guessCategory(name: string): Category {
  return RULES.find(([, pattern]) => pattern.test(name))?.[0] ?? "Others";
}

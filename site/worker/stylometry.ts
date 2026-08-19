type StyleProfile = {
  fw_mean: number[];
  fw_std: number[];
  tau: number;
  ngram_keys: string[];
  ngram_dist: number[];
};

const FUNCTION_WORDS = (`the of and to a in that it is was for as with his he be not by but have you
this had at on i they from she which or we an were her would their there been has when who will more no
if out so up said what its about into than them can only other new some could time these two may then do
first any my now such like our over man me even most made after also did many before must through back years
where much your way well down should because each just those people how too little state good very make world
still see own men work long here between both life being under never same another while last us off might great
go come since against right came take three states himself few house use during without again place around however
home small found thought went say part once general high upon school every don does got united left number course war
until always away something fact though water less public put think almost hand enough far took head yet government
system better set told nothing night end why called didn eyes find going look asked later knew`).split(/\s+/);

const WORD = /[a-z']+/g;
const SLOP = [
  /\bnot\b[^.,;:!?]{1,40},?\s+but\b/gi,
  /\bit'?s\s+(?:worth|important)\s+(?:noting|to note)\b/gi,
  /\blet'?s\s+(?:dive|delve)\b/gi,
  /\b(?:in\s+conclusion|ultimately|at\s+the\s+end\s+of\s+the\s+day)\b/gi,
  /\b(?:in\s+today'?s|in\s+the\s+world\s+of)\b/gi,
];

function functionWordFrequency(text: string): number[] {
  const tokens = text.toLowerCase().match(WORD) || [];
  const counts = new Map<string, number>();
  for (const token of tokens) counts.set(token, (counts.get(token) || 0) + 1);
  const total = Math.max(tokens.length, 1);
  return FUNCTION_WORDS.map((word) => (counts.get(word) || 0) / total);
}

function ngramDistribution(text: string, keys: string[]): number[] {
  const flat = text.toLowerCase().replace(/\s+/g, " ");
  const counts = new Map<string, number>();
  let total = 0;
  for (let index = 0; index <= flat.length - 3; index += 1) {
    const key = flat.slice(index, index + 3);
    counts.set(key, (counts.get(key) || 0) + 1);
    total += 1;
  }
  return keys.map((key) => (counts.get(key) || 0) / Math.max(total, 1));
}

function jsDivergence(left: number[], right: number[]): number {
  const epsilon = 1e-12;
  const pTotal = left.reduce((sum, value) => sum + value + epsilon, 0);
  const qTotal = right.reduce((sum, value) => sum + value + epsilon, 0);
  let divergence = 0;
  for (let index = 0; index < left.length; index += 1) {
    const p = (left[index] + epsilon) / pTotal;
    const q = (right[index] + epsilon) / qTotal;
    const midpoint = (p + q) / 2;
    divergence += 0.5 * p * Math.log(p / midpoint) + 0.5 * q * Math.log(q / midpoint);
  }
  return divergence;
}

export function scoreStyle(profile: StyleProfile, text: string): number {
  if (!text.trim()) return 0;
  if (
    profile.fw_mean.length !== FUNCTION_WORDS.length
    || profile.fw_std.length !== FUNCTION_WORDS.length
    || profile.ngram_keys.length !== profile.ngram_dist.length
  ) throw new Error("The model's style profile is invalid.");
  const frequency = functionWordFrequency(text);
  const distance = frequency.reduce(
    (sum, value, index) => sum + Math.abs((value - profile.fw_mean[index]) / profile.fw_std[index]),
    0,
  ) / FUNCTION_WORDS.length;
  const fw = Math.exp(-(distance ** 2) / (2 * profile.tau ** 2));
  const divergence = jsDivergence(profile.ngram_dist, ngramDistribution(text, profile.ngram_keys));
  const ngram = Math.max(0, 1 - divergence / Math.log(2));
  const hits = SLOP.reduce((sum, pattern) => sum + Array.from(text.matchAll(pattern)).length, 0);
  const markers = Math.max(0, Math.exp(-0.6 * hits));
  return Math.min(1, Math.max(0, 0.5 * fw + 0.3 * ngram + 0.2 * markers));
}

export type { StyleProfile };

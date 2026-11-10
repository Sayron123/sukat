export const PASSWORD_RULES = [
  { label: "8 or more characters", met: (v: string) => v.length >= 8 },
  { label: "A capital letter", met: (v: string) => /[A-Z]/.test(v) },
  { label: "A small letter", met: (v: string) => /[a-z]/.test(v) },
  { label: "A number", met: (v: string) => /[0-9]/.test(v) },
  { label: "A symbol like _ or !", met: (v: string) => /[^A-Za-z0-9\s]/.test(v) },
];

export const WEAK_PASSWORD = "Your password does not meet all the rules yet.";

const GROUPS = ["ABCDEFGHJKLMNPQRSTUVWXYZ", "abcdefghijkmnopqrstuvwxyz", "23456789", "_-!@#$%"];
const SUGGESTED_LENGTH = 16;

export function passwordIsStrong(value: string): boolean {
  return PASSWORD_RULES.every((rule) => rule.met(value));
}

function randomBelow(limit: number): number {
  const ceiling = Math.floor(0x100000000 / limit) * limit;
  const box = new Uint32Array(1);
  do {
    crypto.getRandomValues(box);
  } while (box[0] >= ceiling);
  return box[0] % limit;
}

function pick(chars: string): string {
  return chars[randomBelow(chars.length)];
}

export function suggestPassword(): string {
  const all = GROUPS.join("");
  const out = GROUPS.map(pick);
  while (out.length < SUGGESTED_LENGTH) out.push(pick(all));
  for (let i = out.length - 1; i > 0; i--) {
    const j = randomBelow(i + 1);
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out.join("");
}

type PasswordCredentialClass = new (data: { id: string; password: string }) => Credential;

export async function offerToSavePassword(id: string, password: string): Promise<void> {
  const Credential = (window as unknown as { PasswordCredential?: PasswordCredentialClass }).PasswordCredential;
  if (!Credential) return;
  try {
    await Promise.race([
      navigator.credentials.store(new Credential({ id, password })),
      new Promise((resolve) => setTimeout(resolve, 2000)),
    ]);
  } catch {}
}

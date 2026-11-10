import Link from "next/link";

import { Icon } from "./icons";
import { buttonClass } from "./ui";

export function ScanButton({ href }: { href: string }) {
  return (
    <Link href={href} className={buttonClass("primary", "lg")}>
      <Icon name="camera" />
      Scan
    </Link>
  );
}

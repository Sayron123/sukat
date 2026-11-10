"use client";

import { useState, type ComponentProps } from "react";

import { Icon } from "./icons";
import { Field } from "./ui";

export function PasswordField({
  startVisible = false,
  ...props
}: Omit<ComponentProps<typeof Field>, "type" | "action"> & { startVisible?: boolean }) {
  const [visible, setVisible] = useState(startVisible);
  return (
    <Field
      {...props}
      type={visible ? "text" : "password"}
      action={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          className="grid h-full w-11 shrink-0 place-items-center text-muted hover:text-text focus-visible:outline-offset-[-2px]"
        >
          <Icon name={visible ? "eyeOff" : "eye"} size={20} />
        </button>
      }
    />
  );
}

import type { Metadata } from "next";
import Link from "next/link";

import { H2, LegalPage, List } from "@/components/legal-page";
import { CONTACT_EMAIL } from "@/lib/legal";

export const metadata: Metadata = { title: "Terms · Sukat" };

export default function TermsPage() {
  return (
    <LegalPage title="Terms of Use">
      <p>
        These terms apply when you use Sukat. By creating a store or joining one, you agree to them
        and to our{" "}
        <Link href="/privacy" className="underline">
          Privacy Policy
        </Link>
        .
      </p>

      <H2>Your account</H2>
      <List>
        <li>Give correct information, and keep your password to yourself.</li>
        <li>
          The manager who creates a store is responsible for the store&apos;s account, and for who
          they invite as staff.
        </li>
        <li>Tell us right away if you think someone else is using your account.</li>
      </List>

      <H2>Your data</H2>
      <List>
        <li>Your store&apos;s data belongs to your store. We only use it to run Sukat for you.</li>
        <li>Managers can download it as CSV files at any time.</li>
        <li>
          Only add personal data of other people (like staff names and emails) when you are allowed
          to.
        </li>
      </List>

      <H2>The AI features</H2>
      <p>
        Scans and the AI chat use AI models. They can make mistakes: they can misread a photo or
        give a wrong answer. Always check the items before you save a scan, and check important
        numbers in the History screens.
      </p>

      <H2>Fair use</H2>
      <p>Do not:</p>
      <List>
        <li>try to see another store&apos;s data, or break or overload the service;</li>
        <li>use Sukat for anything illegal;</li>
        <li>share your account with people outside your store.</li>
      </List>
      <p>We may limit or close accounts that break these rules.</p>

      <H2>The service</H2>
      <List>
        <li>
          We work to keep Sukat running and your data safe, but we can&apos;t promise it will
          never be down or never have errors.
        </li>
        <li>
          Sukat helps you track stock. It is not an official receipt or accounting system for tax
          purposes.
        </li>
        <li>
          We are not responsible for losses from wrong stock counts, AI mistakes, or downtime, as
          far as the law allows.
        </li>
      </List>

      <H2>Closing your account</H2>
      <p>
        You can ask us to close your store&apos;s account at any time. Download your data first. We
        delete it as described in the Privacy Policy.
      </p>

      <H2>Changes and law</H2>
      <p>
        If we change these terms, we will update the date at the top and tell store managers about
        big changes. These terms follow the laws of the Philippines.
      </p>

      <H2>Contact</H2>
      <p>
        Email{" "}
        <a href={`mailto:${CONTACT_EMAIL}`} className="underline">
          {CONTACT_EMAIL}
        </a>
        .
      </p>
    </LegalPage>
  );
}

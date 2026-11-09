import type { Metadata } from "next";

import { H2, LegalPage, List } from "@/components/legal-page";
import { CONTACT_EMAIL } from "@/lib/legal";

export const metadata: Metadata = { title: "Privacy · Sukat" };

export default function PrivacyPage() {
  return (
    <LegalPage title="Privacy Policy">
      <p>
        Sukat is an inventory app for hardware stores. This page says what we store, why, who
        else handles it, how long we keep it, and how to reach us. We follow the Philippine Data
        Privacy Act of 2012 (Republic Act 10173).
      </p>

      <H2>What we store</H2>
      <List>
        <li>
          <b>Your account:</b> your name, email, and password. The password is stored only as a
          secure hash: no one can read it, including us.
        </li>
        <li>
          <b>Your store:</b> its name and address (if you add one), and your staff: their names,
          emails, and roles. Invites store the email they were sent to.
        </li>
        <li>
          <b>Store records:</b> products, prices, stock, sales, deliveries, adjustments, voids, and
          who made each one and when.
        </li>
        <li>
          <b>Photos:</b> pictures of handwritten lists or receipts you scan, and what the AI read
          from them.
        </li>
        <li>
          <b>AI use:</b> for each AI request, the date, the feature, the number of tokens, and the
          cost. We do not save your chat questions or answers on our servers.
        </li>
        <li>
          <b>Security records:</b> failed sign-ins and sign-ups (email and IP address), to stop
          password guessing.
        </li>
        <li>
          <b>Technical logs:</b> the page or API path, status, and time of each request, with a
          request number. No passwords, tokens, or search text.
        </li>
      </List>
      <p>
        We do not sell your data, show ads, or use it for anything except running Sukat for your
        store.
      </p>

      <H2>On your phone</H2>
      <p>
        We use one cookie to keep you signed in. It ends when you sign out or after 8 hours. The AI
        chat is kept in the open browser tab only, and is cleared when you sign out.
      </p>

      <H2>Who else handles your data</H2>
      <p>These companies process data for us, only to run Sukat:</p>
      <List>
        <li>
          <b>Anthropic (Claude)</b> and <b>Google (Gemini)</b>: AI models that read scanned photos
          and answer chat questions. They receive the photo or question, and the store data needed
          to answer it. We use their paid API plans, under which they do not use your data to train
          their models.
        </li>
        <li>
          <b>Cloudflare R2</b>: stores scanned photos.
        </li>
        <li>
          <b>Our hosting and database provider</b>: runs the app and stores the data above.
        </li>
        <li>
          <b>Sentry</b> (if turned on): receives error reports, with the error, the page, and the
          request number. We switch off names, emails, cookies, and other personal data in these
          reports.
        </li>
      </List>
      <p>Some of these companies may store data outside the Philippines.</p>

      <H2>How long we keep it</H2>
      <List>
        <li>Account, store records, and photos: while your store uses Sukat.</li>
        <li>
          When a store asks us to close its account: we delete its data within 30 days, except what
          the law requires us to keep.
        </li>
        <li>Failed sign-in and sign-up records: 15 minutes.</li>
        <li>Technical logs and error reports: up to 90 days.</li>
      </List>

      <H2>Your rights</H2>
      <p>Under the Data Privacy Act you can:</p>
      <List>
        <li>ask what data we have about you, and get a copy;</li>
        <li>correct wrong data;</li>
        <li>ask us to delete your data or close your account;</li>
        <li>object to how we use your data;</li>
        <li>
          complain to the National Privacy Commission (
          <a href="https://privacy.gov.ph" className="underline">
            privacy.gov.ph
          </a>
          ).
        </li>
      </List>
      <p>
        Store managers can download the store&apos;s products, transactions, and stock movements at
        any time: More, then Download store data.
      </p>

      <H2>Contact</H2>
      <p>
        For privacy questions or requests, email{" "}
        <a href={`mailto:${CONTACT_EMAIL}`} className="underline">
          {CONTACT_EMAIL}
        </a>
        . We answer within 15 working days.
      </p>

      <H2>Changes</H2>
      <p>
        If we change this policy, we will update the date at the top. For big changes, we will tell
        store managers in the app or by email.
      </p>
    </LegalPage>
  );
}

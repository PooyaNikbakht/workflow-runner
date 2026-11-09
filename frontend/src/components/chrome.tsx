"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useConfig } from "@/components/ConfigProvider";
import { IconGithub } from "@/components/icons";
import { DemoBadge, cx } from "@/components/ui";
import { site } from "@/config/site";

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span aria-hidden="true" className="relative flex h-6 w-6 flex-col items-start justify-between py-0.5">
        <span className="absolute left-[4px] top-1 bottom-1 w-[1.5px] bg-ink" />
        <span className="relative h-2 w-2 rounded-full bg-ink" />
        <span className="relative h-2 w-2 rounded-full bg-ink" />
        <span className="relative h-2.5 w-2.5 -translate-x-[1px] rounded-full bg-accent" />
      </span>
      <span className="text-[15px] font-semibold tracking-tight">{site.productName}</span>
    </span>
  );
}

const NAV = [
  { href: "/", label: "Runs" },
  { href: "/receiver", label: "Webhook receiver" },
];

export function Header() {
  const config = useConfig();
  const pathname = usePathname();
  return (
    <header className="border-b border-line">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-background focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4 sm:px-6">
        <Link href="/" className="rounded-md" aria-label={`${site.productName} home`}>
          <Logo />
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1 text-sm sm:gap-2">
          {config?.demo_mode && (
            <span className="hidden md:inline-flex">
              <DemoBadge />
            </span>
          )}
          {config && !config.demo_mode && (
            <span className="hidden font-mono text-xs text-muted md:inline">Claude {config.model}</span>
          )}
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" || pathname.startsWith("/runs") : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "rounded-md px-2 py-1.5",
                  active ? "font-medium text-ink" : "text-muted hover:text-ink",
                )}
              >
                {item.href === "/receiver" ? (
                  <>
                    <span className="sm:hidden">Receiver</span>
                    <span className="hidden sm:inline">{item.label}</span>
                  </>
                ) : (
                  item.label
                )}
              </Link>
            );
          })}
          {site.repoUrl ? (
            <a
              href={site.repoUrl}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-muted hover:text-ink"
            >
              <IconGithub size={16} />
              <span className="sr-only sm:not-sr-only">Code</span>
            </a>
          ) : null}
        </nav>
      </div>
    </header>
  );
}

export function Footer() {
  return (
    <footer className="mt-16 border-t border-line">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p>
          Built by{" "}
          <a href={site.portfolioUrl} className="font-medium text-ink underline-offset-4 hover:underline">
            {site.author}
          </a>
          . Companies, leads and tickets in the samples are fictional.
        </p>
        <a href={site.githubUrl} className="inline-flex items-center gap-1.5 hover:text-ink">
          <IconGithub size={15} /> GitHub
        </a>
      </div>
    </footer>
  );
}

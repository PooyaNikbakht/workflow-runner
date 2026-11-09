import type { Metadata } from "next";
import { ReceiverView } from "@/components/ReceiverView";

export const metadata: Metadata = { title: "Webhook receiver" };

export default function ReceiverPage() {
  return <ReceiverView />;
}

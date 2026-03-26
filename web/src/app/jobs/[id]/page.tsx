import Link from "next/link";
import JobProgress from "@/components/job-progress";

export default async function JobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  return (
    <main className="min-h-screen flex flex-col items-center px-4 py-16">
      <div className="text-center mb-8">
        <Link href="/" className="text-2xl font-bold text-gray-900 dark:text-gray-100 hover:opacity-80">
          llms.txt Generator
        </Link>
      </div>
      <JobProgress jobId={id} />
    </main>
  );
}

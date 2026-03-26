import UrlForm from "@/components/url-form";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4 py-16">
      <div className="text-center mb-10">
        <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100 mb-3">
          llms.txt Generator
        </h1>
        <p className="text-lg text-gray-500 dark:text-gray-400 max-w-md mx-auto">
          Generate a spec-compliant{" "}
          <a
            href="https://llmstxt.org"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 dark:text-blue-400 hover:underline"
          >
            llms.txt
          </a>{" "}
          file for any website by analyzing its structure and content.
        </p>
      </div>
      <UrlForm />
    </main>
  );
}

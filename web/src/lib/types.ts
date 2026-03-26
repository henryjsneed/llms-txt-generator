export type JobStatus = "PENDING" | "RUNNING" | "COMPLETED" | "FAILED";

export interface Job {
  job_id: string;
  status: JobStatus;
  input_url: string;
  created_at: string;
  updated_at: string;
  result?: {
    llms_txt: string;
    site_title: string;
    site_summary: string;
    pages_analyzed: number;
  };
  error_message?: string;
}

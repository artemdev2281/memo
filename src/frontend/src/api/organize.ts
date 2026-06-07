import { apiFetch } from "./client";

export interface OrganizeFile {
  path: string;
  name: string;
}

export interface OrganizeCluster {
  id: number;
  name: string;
  files: OrganizeFile[];
}

export interface OrganizePreview {
  empty?: boolean;
  clusters: OrganizeCluster[];
  misc: OrganizeFile[];
  single_cluster?: boolean;
}

export interface OrganizePlanCluster {
  folder_name: string;
  files: string[];
}

export function analyzeOrganization(
  folder: string,
  includeSubfolders: boolean,
  paths?: string[],
): Promise<OrganizePreview> {
  return apiFetch<OrganizePreview>("/organize/analyze", {
    method: "POST",
    body: JSON.stringify({
      folder,
      include_subfolders: includeSubfolders,
      ...(paths && paths.length > 0 ? { paths } : {}),
    }),
  });
}

export function applyOrganization(
  folder: string,
  plan: OrganizePlanCluster[],
): Promise<{ folders_created: number; files_moved: number }> {
  return apiFetch<{ folders_created: number; files_moved: number }>(
    "/organize/apply",
    {
      method: "POST",
      body: JSON.stringify({ folder, plan }),
    },
  );
}

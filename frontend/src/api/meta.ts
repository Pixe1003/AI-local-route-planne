import { apiClient } from "./client"
import type { PersonaOption } from "../types/user"

export async function getPersonas(): Promise<PersonaOption[]> {
  return apiClient.get<PersonaOption[], PersonaOption[]>("/meta/personas")
}

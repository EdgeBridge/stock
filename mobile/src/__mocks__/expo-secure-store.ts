export const getItemAsync = jest.fn<Promise<string | null>, [string]>().mockResolvedValue(null)
export const setItemAsync = jest.fn<Promise<void>, [string, string]>().mockResolvedValue(undefined)
export const deleteItemAsync = jest.fn<Promise<void>, [string]>().mockResolvedValue(undefined)

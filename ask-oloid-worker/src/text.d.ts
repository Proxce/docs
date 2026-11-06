// wrangler bundles .txt imports as strings (default Text module rule)
declare module "*.txt" {
  const text: string;
  export default text;
}

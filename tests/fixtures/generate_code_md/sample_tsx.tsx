// Sample .tsx for generate_code_md regression fixture — verifies that
// .tsx files dispatch to the same regex parser as .ts.

export interface ButtonProps {
  label: string;
  onClick: () => void;
}

export const Button = (props: ButtonProps) => {
  return null;
};

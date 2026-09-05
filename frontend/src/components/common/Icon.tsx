import React from "react";

export interface IconProps {
  name: string;
  className?: string;
  style?: React.CSSProperties;
}

export function Icon({ name, className = "", style }: IconProps) {
  return (
    <span className={`material-symbols-outlined ${className}`} style={style}>
      {name}
    </span>
  );
}

export default Icon;


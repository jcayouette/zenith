import { useEffect, useRef, useState } from "react";

type Props = {
  src: string;
  alt: string;
  className?: string;
};

/** Keep the last decoded frame visible until the next JPEG is ready, so live updates do not flash black. */
export default function LiveFrame({ src, alt, className }: Props) {
  const [front, setFront] = useState(src);
  const [back, setBack] = useState<string | null>(null);
  const frontRef = useRef(src);
  frontRef.current = front;

  useEffect(() => {
    if (!src || src === frontRef.current) return;
    setBack(src);
  }, [src]);

  const imgClass = className ?? "block h-full w-full bg-black object-fill";

  return (
    <>
      {front ? (
        <img src={front} alt={alt} draggable={false} decoding="sync" className={imgClass} />
      ) : null}
      {back ? (
        <img
          src={back}
          alt=""
          draggable={false}
          decoding="async"
          className={`${imgClass} pointer-events-none absolute inset-0 opacity-0`}
          onLoad={() => {
            setFront(back);
            setBack(null);
          }}
          onError={() => setBack(null)}
        />
      ) : null}
    </>
  );
}

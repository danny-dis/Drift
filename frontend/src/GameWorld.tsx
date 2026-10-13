import { forwardRef } from "react";
import OfficeCanvas, { type OfficeCanvasHandle } from "./office/OfficeCanvas";
import type { OfficeStatus } from "./office/character";

export interface GameWorldHandle extends OfficeCanvasHandle {}
type Props = OfficeStatus & { animated?: boolean };

const GameWorld = forwardRef<GameWorldHandle, Props>((props, ref) => (
  <OfficeCanvas ref={ref} status={props} animated={props.animated ?? false}
    label={`Drift's furnished isometric office. State: ${props.state}.`} />
));
GameWorld.displayName = "GameWorld";
export default GameWorld;

from selfdrive.controls.lib.pid import PIController
from selfdrive.controls.lib.latcontrol import LatControl, MIN_STEER_SPEED
from cereal import log

CURVATURE_SCALE = 200


class LatControlCrayCray(LatControl):
  def __init__(self, CP, CI):
    super().__init__(CP, CI)
    self.pid = PIController((CP.lateralTuning.craycray.kpBP, CP.lateralTuning.craycray.kpV),
                            (CP.lateralTuning.craycray.kiBP, CP.lateralTuning.craycray.kiV),
                            k_f=CP.lateralTuning.craycray.kf, pos_limit=1.0, neg_limit=-1.0)
    self.get_steer_feedforward = CI.get_steer_feedforward_function()
    self.steer_max = 1.0
    self.pid.pos_limit = self.steer_max
    self.pid.neg_limit = -self.steer_max
    self.use_steering_angle = False

  def reset(self):
    super().reset()
    self.pid.reset()

  def update(self, active, CS, CP, VM, params, last_actuators, desired_curvature, desired_curvature_rate, llk):
    pid_log = log.ControlsState.LateralPIDState.new_message()
    pid_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    pid_log.steeringRateDeg = float(CS.steeringRateDeg)

    #pid_log.steeringAngleDesiredDeg = angle_steers_des
    #pid_log.angleError = angle_steers_des - CS.steeringAngleDeg
    if CS.vEgo < MIN_STEER_SPEED or not active:
      output_torque = 0.0
      pid_log.active = False
      self.pid.reset()
    else:
      # TODO lateral acceleration works great at high speed, not so much at low speed
      if self.use_steering_angle:
        actual_curvature = VM.calc_curvature(-(CS.steeringAngleDeg - params.angleOffsetDeg), CS.vEgo, params.roll)
      else:
        actual_curvature = llk.angularVelocityCalibrated.value[2] / CS.vEgo
      desired_lateral_accel = desired_curvature * CS.vEgo**2
      actual_lateral_accel = actual_curvature * CS.vEgo**2

      setpoint = desired_lateral_accel + CURVATURE_SCALE * desired_curvature
      measurement = actual_lateral_accel + CURVATURE_SCALE * actual_curvature

      output_torque = self.pid.update(setpoint, measurement, override=CS.steeringPressed,
                                      feedforward=desired_lateral_accel, speed=CS.vEgo)
      pid_log.angleError = setpoint - measurement
      pid_log.active = True
      pid_log.p = self.pid.p
      pid_log.i = self.pid.i
      pid_log.f = self.pid.f
      #TODO left is positive in this log
      pid_log.output = -output_torque
      pid_log.saturated = self._check_saturation(self.steer_max - abs(output_torque) < 1e-3, CS)

    #TODO left is positive in this convention
    return -output_torque, 0.0, pid_log

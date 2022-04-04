from selfdrive.controls.lib.pid import PIController
from selfdrive.controls.lib.latcontrol import LatControl, MIN_STEER_SPEED
from cereal import log

CURVATURE_SCALE = 400


class LatControlTorque(LatControl):
  def __init__(self, CP, CI):
    super().__init__(CP, CI)
    self.pid = PIController(([0.0], [CP.lateralTuning.torque.kp]),
                            ([0.0], [CP.lateralTuning.torque.ki]),
                            k_f=CP.lateralTuning.torque.kf, pos_limit=1.0, neg_limit=-1.0)
    self.get_steer_feedforward = CI.get_steer_feedforward_function()
    self.steer_max = 1.0
    self.pid.pos_limit = self.steer_max
    self.pid.neg_limit = -self.steer_max
    self.use_steering_angle = CP.lateralTuning.torque.useSteeringAngle

  def reset(self):
    super().reset()
    self.pid.reset()

  def update(self, active, CS, CP, VM, params, last_actuators, desired_curvature, desired_curvature_rate, llk):
    pid_log = log.ControlsState.LateralTorqueState.new_message()

    if CS.vEgo < MIN_STEER_SPEED or not active:
      output_torque = 0.0
      pid_log.active = False
      self.pid.reset()
    else:
      # TODO lateral acceleration works great at high speed, not so much at low speed
      if self.use_steering_angle:
        actual_curvature = -VM.calc_curvature(CS.steeringAngleDeg - params.angleOffsetDeg, CS.vEgo, params.roll)
      else:
        actual_curvature = llk.angularVelocityCalibrated.value[2] / CS.vEgo
      desired_lateral_accel = desired_curvature * CS.vEgo**2
      actual_lateral_accel = actual_curvature * CS.vEgo**2

      setpoint = desired_lateral_accel + CURVATURE_SCALE * desired_curvature
      measurement = actual_lateral_accel + CURVATURE_SCALE * actual_curvature
      pid_log.error = setpoint - measurement

      output_torque = self.pid.update(setpoint, measurement, override=CS.steeringPressed,
                                      feedforward=desired_lateral_accel, speed=CS.vEgo)
      pid_log.active = True
      pid_log.p = self.pid.p
      pid_log.i = self.pid.i
      pid_log.f = self.pid.f
      pid_log.output = -output_torque
      pid_log.saturated = self._check_saturation(self.steer_max - abs(output_torque) < 1e-3, CS)

    #TODO left is positive in this convention
    return -output_torque, 0.0, pid_log

//! Source-order configuration time facts. This grammar does not change SQL scalars.
use super::literal::Lit;
use super::model::ValueKind;

pub const CONFIGURATION_GENERATED_TIME_RULE: &str = "gateway-vnext/configuration-generated-time/v1";
const DAY_US: i64 = 86_400_000_000;

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ConfigurationGeneratedTime {
    pub status: &'static str,
    pub valid_count: usize,
    pub empty_count: usize,
    pub invalid_count: usize,
    pub last_valid_source_row: Option<usize>,
    pub max_valid_source_row: Option<usize>,
    selected: Option<i64>,
    maximum: Option<i64>,
}

impl ConfigurationGeneratedTime {
    pub fn selected_time_utc(&self) -> Option<String> {
        self.selected.map(format_utc)
    }
    pub fn max_valid_time_utc(&self) -> Option<String> {
        self.maximum.map(format_utc)
    }
    pub fn last_not_max(&self) -> bool {
        self.selected < self.maximum
    }

    pub(crate) fn observe(&mut self, value: &Lit<'_>, kind: &ValueKind) {
        let row = self.row_count() + 1;
        if matches!(value, Lit::Null) {
            self.empty_count += 1;
            return;
        }
        if !matches!(
            kind,
            ValueKind::Str | ValueKind::Enum | ValueKind::DateTime | ValueKind::Timestamp
        ) {
            self.invalid_count += 1;
            return;
        }
        let Ok(text) = super::convert::require_text(value, 0) else {
            self.invalid_count += 1;
            return;
        };
        let text = trim_allowed(text.as_bytes());
        if text.is_empty() {
            self.empty_count += 1;
            return;
        }
        if let Some(instant) = parse_time(text) {
            self.valid_count += 1;
            self.selected = Some(instant);
            self.last_valid_source_row = Some(row);
            if self.maximum.is_none_or(|previous| instant > previous) {
                self.maximum = Some(instant);
                self.max_valid_source_row = Some(row);
            }
        } else {
            self.invalid_count += 1;
        }
    }

    pub(crate) fn merge(&mut self, other: &Self) {
        let offset = self.row_count();
        if let Some(selected) = other.selected {
            self.selected = Some(selected);
            self.last_valid_source_row = other.last_valid_source_row.map(|row| offset + row);
        }
        if other.maximum.is_some() && (self.maximum.is_none() || other.maximum > self.maximum) {
            self.maximum = other.maximum;
            self.max_valid_source_row = other.max_valid_source_row.map(|row| offset + row);
        }
        self.valid_count += other.valid_count;
        self.empty_count += other.empty_count;
        self.invalid_count += other.invalid_count;
    }

    fn row_count(&self) -> usize {
        self.valid_count + self.empty_count + self.invalid_count
    }
    pub(crate) fn finish(mut self, presence: &'static str) -> Self {
        self.status = if presence != "PRESENT" {
            presence
        } else if self.valid_count > 0 {
            "VALID"
        } else if self.row_count() == 0 {
            "NO_ROWS"
        } else if self.invalid_count == 0 {
            "NO_VALUE"
        } else {
            "NO_VALID_VALUE"
        };
        self
    }
}

fn trim_allowed(mut text: &[u8]) -> &[u8] {
    while text
        .first()
        .is_some_and(|c| matches!(c, b' ' | b'\t' | b'\r' | b'\n'))
    {
        text = &text[1..];
    }
    while text
        .last()
        .is_some_and(|c| matches!(c, b' ' | b'\t' | b'\r' | b'\n'))
    {
        text = &text[..text.len() - 1];
    }
    text
}

fn number(text: &[u8]) -> Option<i64> {
    text.iter().try_fold(0, |n, c| {
        if c.is_ascii_digit() {
            Some(n * 10 + i64::from(*c - b'0'))
        } else {
            None
        }
    })
}
fn days_before_year(year: i64) -> i64 {
    let y = year - 1;
    365 * y + y / 4 - y / 100 + y / 400
}
fn month_days(year: i64, month: i64) -> i64 {
    match month {
        2 => {
            if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) {
                29
            } else {
                28
            }
        }
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
}
fn parse_time(text: &[u8]) -> Option<i64> {
    if !(19..=32).contains(&text.len())
        || text[4] != b'-'
        || text[7] != b'-'
        || !matches!(text[10], b'T' | b' ')
        || text[13] != b':'
        || text[16] != b':'
    {
        return None;
    }
    let year = number(&text[0..4])?;
    let month = number(&text[5..7])?;
    let day = number(&text[8..10])?;
    let hour = number(&text[11..13])?;
    let minute = number(&text[14..16])?;
    let second = number(&text[17..19])?;
    if !(1..=9999).contains(&year)
        || !(1..=12).contains(&month)
        || !(1..=month_days(year, month)).contains(&day)
        || hour > 23
        || minute > 59
        || second > 59
    {
        return None;
    }
    let mut position = 19;
    let mut micros = 0;
    if text.get(position) == Some(&b'.') {
        position += 1;
        let start = position;
        while text.get(position).is_some_and(u8::is_ascii_digit) {
            position += 1;
        }
        let count = position - start;
        if !(1..=6).contains(&count) {
            return None;
        }
        micros = number(&text[start..position])? * 10_i64.pow(u32::try_from(6 - count).ok()?);
    }
    let offset = match &text[position..] {
        [] | [b'Z'] => 0,
        [sign @ (b'+' | b'-'), h1, h2, b':', m1, m2] => {
            let hours = number(&[*h1, *h2])?;
            let minutes = number(&[*m1, *m2])?;
            if hours > 14 || minutes > 59 || (hours == 14 && minutes != 0) {
                return None;
            }
            (hours * 60 + minutes) * if *sign == b'+' { 1 } else { -1 }
        }
        _ => return None,
    };
    let days =
        days_before_year(year) + (1..month).map(|m| month_days(year, m)).sum::<i64>() + day - 1;
    let result =
        days * DAY_US + (hour * 3600 + minute * 60 + second - offset * 60) * 1_000_000 + micros;
    (0..days_before_year(10000) * DAY_US)
        .contains(&result)
        .then_some(result)
}
fn format_utc(instant: i64) -> String {
    let days = instant / DAY_US;
    let mut lower = 1;
    let mut upper = 10000;
    while lower + 1 < upper {
        let middle = (lower + upper) / 2;
        if days_before_year(middle) <= days {
            lower = middle;
        } else {
            upper = middle;
        }
    }
    let year = lower;
    let mut day = days - days_before_year(year);
    let mut month = 1;
    while day >= month_days(year, month) {
        day -= month_days(year, month);
        month += 1;
    }
    let clock = instant % DAY_US;
    let hour = clock / 3_600_000_000;
    let minute = clock / 60_000_000 % 60;
    let second = clock / 1_000_000 % 60;
    let micros = clock % 1_000_000;
    let fraction = if micros == 0 {
        String::new()
    } else {
        format!(".{micros:06}").trim_end_matches('0').to_owned()
    };
    format!(
        "{year:04}-{month:02}-{:02}T{hour:02}:{minute:02}:{second:02}{fraction}Z",
        day + 1
    )
}

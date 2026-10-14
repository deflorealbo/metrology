ORDERS = [
  { id: 1, customer: "Alice", items: [100, 250, 30],  paid: true  },
  { id: 2, customer: "Bob",   items: [500],           paid: false },
  { id: 3, customer: "Carol", items: [50, 70, 120, 90], paid: true },
  { id: 4, customer: "Dave",  items: [],              paid: false }
].freeze

def describe_order(order)
  total = 0

  for price in order[:items]
    if price.is_a?(Numeric) && price > 0
      discount = 0
      if price >= 100
        case price
        when 100...300 then discount += 5
        when 300...1000 then discount += 10
        else 
          if discount + 15 <= 20
            discount += 15
          else
            discount = 20
          end
        end
      end
      total += price*(100 - discount)*0.01
    else
      total += 0
    end
  end

  total
end

def status_of(order)
  if order[:paid]
    total = describe_order(order)
    if total >= 300
      "оплачен, дорогой"
    else
      "оплачен, дешевый"
    end
  else
    if order[:items].empty?
      "не оплачен, пустой"
    else
      i = 0
      has_expensive = false
      until i >= order[:items].length || has_expensive
        # Уровень 3: ветвление внутри until
        if order[:items][i] >= 300
          has_expensive = true
        end
        i += 1
      end

       has_expensive ? "не оплачен, дорогой" : "не оплачен, дешевый"
    end
  end
end

def count_unpaid_orders(orders)
  count = 0
  i = 0

  loop do
    break if i >= orders.length

    if !orders[i][:paid] && !orders[i][:items].empty?
      count += 1
    end

    i += 1
  end

  puts "\nНеоплаченных заказов: #{count}"
end


def paid_items(orders)
  count = 0
  i = 0

  while i < orders.length
    if orders[i][:paid]
      count += orders[i][:items].length
    end
    i += 1
  end

  puts "Количество товаров в оплаченных заказах: #{count}"
end

  puts "==== Отчёт по заказам ===="

  ORDERS.each do |order|
    status = status_of(order)
    total  = describe_order(order)

    line = case status
           when "оплачен, дорогой"   then "★ #{order[:customer]}: #{total} руб. Товар оплачен, дорогой."
           when "оплачен, дешевый"    then "✓ #{order[:customer]}: #{total} руб. Товар оплачен, дешевый."
           when "не оплачен, дорогой" then "! #{order[:customer]}: долг #{total} руб. Товар не оплачен, дорогой."
           when "не оплачен, дешевый" then "· #{order[:customer]}: долг #{total} руб. Товар не оплачен, дешевый."
           else                            "? #{order[:customer]}: нет данных."
           end

    unless order[:items].empty?
      puts line
    else
      puts line + " (нет товаров)"
    end
  end

  count_unpaid_orders(ORDERS)
  paid_items(ORDERS)